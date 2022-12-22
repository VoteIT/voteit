from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from itertools import count
from logging import getLogger
from typing import Generator
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db import transaction
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.text import slugify
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField
from django_fsm import transition

from voteit.core.abcs import MeetingContext
from voteit.core.abcs import OrganisationContext
from voteit.core.fields import RichTextField
from voteit.core.models import BaseContent
from voteit.core.models import RoleContextMixin
from voteit.core.models import Roles
from voteit.core.models import User
from voteit.core.permissions import NOT_ALLOWED
from voteit.core.utils import relaxed_clean_html
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.workflows import MeetingWf
from voteit.organisation.permissions import OrgPermissions
from voteit.poll.utils import get_electoral_policy_registry
from voteit.proposal import DEFAULT_PROPOSAL_ID_POLICY
from voteit.proposal.utils import get_proposal_id_registry

if TYPE_CHECKING:
    from voteit.access_policy.models import AccessPolicy
    from voteit.components.models import MeetingComponent
    from voteit.poll.models import ElectoralRegister
    from voteit.poll.abcs import ElectoralRegisterPolicy
    from voteit.organisation.models import Organisation
    from voteit.participant_number.models import PNSystem
    from voteit.presence.models import PresenceSystem
    from voteit.presence.models import PresenceCheck
    from voteit.speaker.models import SpeakerListSystem
    from voteit.proposal.abcs import ProposalIDPolicy

__all__ = (
    "Meeting",
    "MeetingRoles",
    "MeetingGroup",
    "GroupRole",
    "GroupMembership",
)


logger = getLogger(__name__)


class MeetingRoles(Roles, MeetingContext):
    """Contains assigned meeting roles for a specific meeting and user"""

    name = "meeting_roles"

    user: User = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meeting_roles"
    )
    context: Meeting = models.ForeignKey(
        "Meeting", on_delete=models.CASCADE, related_name="roles"
    )

    @property
    def meeting(self) -> Meeting:
        return self.context

    class Meta:
        verbose_name = verbose_name_plural = "Meeting roles"
        unique_together = (("user", "context"),)

    def get_additional_data(self):
        """
        Extra annotations for auditlog
        """
        return {"m": self.context.pk, "o": self.context.organisation_id}

    exporters = {"meeting": {"meeting_kw": "context"}}
    importers = {
        "meeting": {"remap_relations": {"meeting": "context"}},
        "organisation": {
            "remap_relations": {
                "meeting": "context",
            }
        },
    }


class Meeting(BaseContent, RoleContextMixin, MeetingContext, OrganisationContext):
    name = "meeting"
    title: str = models.CharField(max_length=100)
    body: str = RichTextField(blank=True, default="", html_cleaner=relaxed_clean_html)
    state: str = FSMField(
        default=MeetingWf.initial, choices=MeetingWf.choices(), editable=False
    )
    start_time: datetime | None = models.DateTimeField(
        verbose_name="When the meeting starts/started.", null=True, blank=True
    )
    end_time: datetime | None = models.DateTimeField(
        verbose_name="When the meeting ends/ended.", null=True, blank=True
    )
    public: bool = models.BooleanField(
        verbose_name="Is this meeting viewable by anyone?", default=False
    )
    visible_in_lists: bool = models.BooleanField(
        verbose_name="Show basic meeting details in lists?", default=False
    )
    # group_votes_policy_name: str|None = models.CharField(
    #     verbose_name="Voting power comes from groups rather than individuals",
    #     max_length=30,
    #     null=True,
    #     blank=True,
    # )
    # group_roles_policy_name: str|None = models.CharField(
    #     verbose_name="System for dynamic roles within groups",
    #     max_length=30,
    #     null=True,
    #     blank=True,
    # )
    er_policy_name: str | None = models.CharField(
        verbose_name="ID of used electoral policy",
        max_length=30,
        null=True,
        blank=True,
    )
    proposal_id_policy_name: str | None = models.CharField(
        verbose_name="Proposal ID policy name, defaults to system standard",
        max_length=30,
        null=True,
        blank=True,
    )
    organisation: Organisation | None = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="meetings",
    )
    archive_after: datetime | None = models.DateTimeField(null=True, editable=False)
    delete_requested: datetime | None = models.DateTimeField(null=True, editable=False)
    pre_delete_state: str | None = models.CharField(
        max_length=30, null=True, editable=False
    )

    roles_cls = MeetingRoles
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through=MeetingRoles
    )

    exporters = {
        "meeting": {
            "meeting_kw": "pk",
            "ignore_fields": (
                "archive_after",
                "start_time",
                "end_time",
            ),
        }
    }
    importers = {
        "meeting": {},
        "organisation": {"remap_relations": {"user": {"last_modified_by", "author"}}},
    }

    @cached_property
    def pid_policy(self) -> ProposalIDPolicy:
        reg = get_proposal_id_registry()
        if self.proposal_id_policy_name:
            return reg[self.proposal_id_policy_name](self)
        return reg[DEFAULT_PROPOSAL_ID_POLICY](self)

    @cached_property
    def er_policy(self) -> ElectoralRegisterPolicy:
        return self._er_policy()

    @cached_property
    def latest_er(self) -> ElectoralRegister | None:
        return self.get_latest_er()

    def _er_policy(self):
        reg = get_electoral_policy_registry()
        return reg[self.er_policy_name](self)

    def get_latest_er(self) -> ElectoralRegister | None:
        return (
            self.electoral_registers.filter(meeting=self).order_by("-created").first()
        )

    def get_access_policies(self, only_active=True) -> Generator[AccessPolicy]:
        from voteit.access_policy.registries import access_policies

        query = {}
        if only_active:
            query["active"] = True
        for ap in access_policies.values():
            obj = ap.objects.filter(meeting=self, **query).first()
            if obj:
                yield obj  # All of them are 1-1 relations

    def valid_er_policy_guard(self) -> bool:
        return self.er_policy_name in get_electoral_policy_registry()

    valid_er_policy_guard.title = _("Must have valid electoral register policy name")

    @transition(
        field=state,
        source=MeetingWf.ONGOING,
        target=MeetingWf.UPCOMING,
        permission=MeetingPermissions.MODERATE,
        custom={"title": _("Back to upcoming")},
    )
    def upcoming(self):
        pass

    @transition(
        field=state,
        source=[MeetingWf.UPCOMING, MeetingWf.CLOSED],
        target=MeetingWf.ONGOING,
        permission=MeetingPermissions.MODERATE,
        conditions=[valid_er_policy_guard],
        custom={"title": _("Make ongoing")},
    )
    def ongoing(self):
        self.start_time = timezone.now()

    @transition(
        field=state,
        source=MeetingWf.ONGOING,
        target=MeetingWf.CLOSED,
        permission=MeetingPermissions.MODERATE,
        custom={"title": _("Close")},
    )
    def close(self):
        self.end_time = timezone.now()

    @transition(
        field=state,
        source=MeetingWf.CLOSED,
        target=MeetingWf.ARCHIVING,
        permission=MeetingPermissions.ARCHIVE,
        custom={"title": _("Request archiving")},
    )
    def request_archiving(self):
        self.archive_after = now() + timedelta(days=3)
        # FIXME: Do lots of checks here later on, make sure ais are closed etc

    @transition(
        field=state,
        source=MeetingWf.ARCHIVING,
        target=MeetingWf.CLOSED,
        permission=MeetingPermissions.ARCHIVE,
        custom={"title": _("Abort archiving")},
    )
    def abort_archiving(self):
        self.archive_after = None

    @transition(
        field=state,
        source="+",
        target=MeetingWf.ARCHIVED,
        permission=NOT_ALLOWED,
    )
    def archive(self):
        from voteit.meeting.signals import archive_meeting  # Avoid circular import

        with transaction.atomic():
            archive_meeting.send(sender=self.__class__, meeting=self)

    @transition(
        field=state,
        source=[
            MeetingWf.UPCOMING,
            MeetingWf.ONGOING,
            MeetingWf.CLOSED,
            MeetingWf.ARCHIVED,
            MeetingWf.ARCHIVING,
        ],
        target=MeetingWf.DELETING,
        permission=MeetingPermissions.DELETE,
        custom={"title": _("Request delete...")},
    )
    def request_delete(self):
        self.pre_delete_state = self.state
        self.delete_requested = now()

    @transition(
        field=state,
        source=MeetingWf.DELETING,
        target=None,
        permission=MeetingPermissions.DELETE,
        custom={"title": _("Abort delete")},
    )
    def abort_delete(self):
        self.state = self.pre_delete_state
        self.delete_requested = None

    @property
    def is_archived(self):
        return self.state in MeetingWf.archived_states

    @property
    def meeting(self) -> Meeting:
        """
        To fulfill the MeetingContext ABC.
        """
        return self

    class QuerySet(models.QuerySet):
        def for_user(self, user: User):
            if user.is_superuser:
                return user.organisation.meetings.all()
            if user.organisation is None:
                return self.none()
            if user.has_perm(OrgPermissions.MANAGE, user.organisation):
                return user.organisation.meetings.all()
            else:
                return user.organisation.meetings.filter(
                    models.Q(visible_in_lists=True)
                    | models.Q(participants=user)
                    | models.Q(public=True)
                ).distinct()

    class Manager(models.Manager):
        def get_queryset(self):
            return Meeting.QuerySet(self.model, using=self._db)

        def for_user(self, user: User):
            return self.get_queryset().for_user(user)

    objects = Manager()
    groups: models.QuerySet
    invites: models.QuerySet
    invite_dispatches: models.QuerySet
    electoral_registers: models.QuerySet
    agenda_items: models.QuerySet
    last_read_set: models.QuerySet
    pn_system: PNSystem | None
    presence_system: PresenceSystem | None
    presence_checks: PresenceCheck.Manager
    polls: models.QuerySet
    reaction_buttons: models.QuerySet
    speaker_systems: models.QuerySet[SpeakerListSystem]
    components: models.QuerySet[MeetingComponent]
    roles: models.QuerySet[MeetingRoles]


class MeetingGroup(BaseContent, MeetingContext):
    name: str = "meeting_group"
    title: str = models.CharField(max_length=100, default="")
    groupid: str = models.CharField(max_length=100, null=True)
    meeting: Meeting = models.ForeignKey(
        "Meeting", on_delete=models.CASCADE, related_name="groups"
    )
    # votes: int | None = models.IntegerField(blank=True, null=True)
    # TODO: Remove 'members' after migrating existing data, and then either rename 'role_members',
    # TODO: or add relay property.
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="meeting_groups",
        through="GroupMembership",
    )

    def save(
        self, force_insert=False, force_update=False, using=None, update_fields=None
    ):
        if self.groupid is None:
            if self.meeting.organisation is None:  # For testing
                user_qs = User.objects.all()
            else:
                user_qs = self.meeting.organisation.users.all()
            group_qs = self.meeting.groups.all()
            base = groupid = slugify(self.title)
            for i in count(1):
                if not (
                    user_qs.filter(userid=groupid).exists()
                    or group_qs.filter(groupid=groupid).exists()
                ):
                    self.groupid = groupid
                    break
                groupid = f"{base}-{i}"
        super().save(force_insert, force_update, using, update_fields)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("groupid", "meeting"), name="unique_meeting_id"
            ),
        )

    exporters = {"meeting": {}}
    importers = {
        "meeting": {},
        "organisation": {"remap_relations": {"user": {"last_modified_by", "author"}}},
    }

    # Type annotations - relations
    proposals: models.QuerySet
    discussions: models.QuerySet
    objects: models.Manager[MeetingGroup]


class GroupRole(MeetingContext):
    """
    Dynamic group roles for a meeting. These can be automatically created from a meeting dialect,
    or created by a meeting moderator.
    """

    title: str = models.CharField(max_length=100)
    meeting: Meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="group_roles"
    )
    can_propose_as: bool = models.BooleanField("Can propose as group", default=False)
    can_discuss_as: bool = models.BooleanField("Can discuss as group", default=False)
    roles: list[str] = ArrayField(
        models.CharField(
            max_length=20,
        ),
    )
    # Groups should be able to map to a meeting dialect, which will define if they're editable, etc.
    # dialect_group = models.CharField(null=True, blank=True, max_length=40, unique=True)
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        through="GroupMembership",
        related_name="assigned_group_roles",
    )

    class Meta:
        ordering = ["title"]  # Should group roles have a manual order?
        constraints = [
            models.UniqueConstraint(
                fields=["title", "meeting"], name="unique_meeting_grp_title"
            ),
        ]
        verbose_name = "Group role"
        verbose_name_plural = "Group roles"

    def __str__(self):
        return self.title

    # Annotations
    objects: models.Manager[GroupRole]


class GroupMembership(models.Model):
    """
    Join table for users and group roles.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )
    meeting_group = models.ForeignKey(
        MeetingGroup, on_delete=models.CASCADE, related_name="role_assignments"
    )
    role = models.ForeignKey(
        GroupRole, on_delete=models.CASCADE, related_name="+", null=True, blank=True
    )

    # Annotations
    objects: models.Manager[GroupMembership]
