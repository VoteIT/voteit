from __future__ import annotations

from datetime import datetime
from logging import getLogger
from random import sample
from string import ascii_lowercase
from typing import TYPE_CHECKING, Generator

from auditlog.registry import auditlog
from django.conf import settings
from django.db import models
from django.utils.functional import cached_property
from django.utils.text import slugify
from rules.contrib.models import RulesModelMixin
from statemachine.mixins import MachineMixin

from voteit.core import PERM
from voteit.core.abcs import MeetingContext, OrganisationContext
from voteit.core.decorators import ensure_atomic
from voteit.core.fields import RichTextField, RolesField
from voteit.core.models import BaseContent, RoleContextMixin, Roles, User
from voteit.core.utils import relaxed_clean_html
from voteit.meeting import roles
from voteit.meeting.statemachines import MeetingStateMachine
from voteit.poll.utils import (
    get_electoral_policy_registry,
    get_vote_transfer_policy_registry,
)
from voteit.proposal import DEFAULT_PROPOSAL_ID_POLICY
from voteit.proposal.utils import get_proposal_id_registry
from voteit.stats.registry import history_log

if TYPE_CHECKING:
    from voteit.access_policy.models import AccessPolicy
    from voteit.active.models import ActiveUser
    from voteit.components.models import MeetingComponent
    from voteit.core.role import Role
    from voteit.discussion.models import DiscussionPost
    from voteit.organisation.models import Organisation
    from voteit.participant_number.models import PNSystem
    from voteit.participant_tags.models import ParticipantTags
    from voteit.poll.abcs import ElectoralRegisterPolicy, VoteTransferPolicy
    from voteit.poll.models import ElectoralRegister, VoteTransfer
    from voteit.presence.models import PresenceCheck
    from voteit.proposal.abcs import ProposalIDPolicy
    from voteit.proposal.models import Proposal
    from voteit.room.models import Room
    from voteit.speaker.models import SpeakerListSystem

__all__ = (
    "Meeting",
    "MeetingRoles",
    "MeetingGroup",
    "GroupRole",
    "GroupMembership",
)


logger = getLogger(__name__)


def _rnd_role_id():
    return "".join(sample(ascii_lowercase, 8))


@auditlog.register(
    include_fields=[
        "user",
        "context",
        "assigned",
    ],
)
class MeetingRoles(Roles, MeetingContext):
    """
    Contains assigned meeting roles for a specific meeting and user
    """

    name = "meeting_roles"
    valid_roles = {
        roles.ROLE_DISCUSSER: roles.ROLE_DISCUSSER,
        roles.ROLE_MODERATOR: roles.ROLE_MODERATOR,
        roles.ROLE_PARTICIPANT: roles.ROLE_PARTICIPANT,
        roles.ROLE_POTENTIAL_VOTER: roles.ROLE_POTENTIAL_VOTER,
        roles.ROLE_PROPOSER: roles.ROLE_PROPOSER,
    }

    user: User = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meeting_roles"
    )
    context: Meeting = models.ForeignKey(
        "Meeting", on_delete=models.CASCADE, related_name="roles"
    )
    assigned: list[Role] = RolesField(
        max_length=60,
        role_choices=valid_roles.values(),
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


@history_log("organisation")
@auditlog.register(
    include_fields=[
        "title",
        "body",
        "state",
        "public",
        "visible_in_lists",
        "group_votes_active",
        "group_roles_active",
        "er_policy_name",
        "proposal_id_policy_name",
        "installed_dialect",
        "organisation",
    ],
)
class Meeting(
    BaseContent,
    RoleContextMixin,
    MeetingContext,
    OrganisationContext,
    RulesModelMixin,
    MachineMixin,
):
    """
    The primary container for all democratic activity within VoteIT.

    Every agenda item, proposal, poll, and discussion belongs to a meeting.
    Lifecycle (``MeetingStateMachine``): ``upcoming → ongoing ↔ closed → archiving → archived``,
    plus a ``deleting`` state reachable from any live state.

    Key configuration fields:
    - ``er_policy_name`` — names the electoral register policy used to determine
      voter eligibility and weight. Required before the meeting can go ``ongoing``.
    - ``group_votes_active`` — voting power comes from groups rather than individuals.
    - ``group_roles_active`` — dynamic role assignment through group membership.
    - ``installed_dialect`` — name of the active YAML dialect configuration.
    - ``proposal_id_policy_name`` — pluggable proposal-ID generator (default: ``userid``).

    Access: participants join via ``MeetingRoles`` (M2M through-model). Superusers
    and org managers can always see all meetings; regular users only see meetings
    where they are a participant, or that are public/visible-in-lists.
    """

    state_machine_name = "voteit.meeting.statemachines.MeetingStateMachine"
    state_machine_attr = "sm"
    sm: MeetingStateMachine

    name = "meeting"
    _er_policy_name = None

    title: str = models.CharField(max_length=100)
    body: str = RichTextField(blank=True, default="", html_cleaner=relaxed_clean_html)
    state: str = models.CharField(
        default=MeetingStateMachine.initial_state.value,
        choices=[(s.value, str(s.name)) for s in MeetingStateMachine.states],
        max_length=20,
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
    group_votes_active: bool = models.BooleanField(
        verbose_name="Voting power comes from groups rather than individuals",
        default=False,
    )
    group_roles_active: bool = models.BooleanField(
        verbose_name="System for dynamic roles within groups",
        default=False,
    )
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
    installed_dialect: str | None = models.CharField(
        verbose_name="Configuration steps for roles, groups or similar + possible restrictions.",
        max_length=60,
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep track of original value
        self._er_policy_name = self.er_policy_name

    @cached_property
    def pid_policy(self) -> ProposalIDPolicy:
        reg = get_proposal_id_registry()
        if self.proposal_id_policy_name:
            return reg[self.proposal_id_policy_name](self)
        return reg[DEFAULT_PROPOSAL_ID_POLICY](self)

    @property
    def er_policy(self) -> ElectoralRegisterPolicy:
        reg = get_electoral_policy_registry()
        return reg[self.er_policy_name](self)

    @cached_property
    def latest_er(self) -> ElectoralRegister | None:
        return self.get_latest_er()

    def get_latest_er(self) -> ElectoralRegister | None:
        return (
            self.electoral_registers.filter(meeting=self).order_by("-created").first()
        )

    def signal_er_policy_changed(self):
        """
        Method should never signal unless it has a valid ER policy
        """
        try:
            self.er_policy
        except KeyError:  # We don't want to check those kinds of errors here
            return
        from voteit.meeting.signals import er_policy_changed

        er_policy_changed.send(sender=self.er_policy.__class__, instance=self.er_policy)

    def get_access_policies(self, only_active=True) -> Generator[AccessPolicy]:
        from voteit.access_policy.registries import access_policies

        query = {}
        if only_active:
            query["active"] = True
        for ap in access_policies.values():
            if obj := ap.objects.filter(meeting=self, **query).first():
                yield obj  # All of them are 1-1 relations

    @property
    def vote_transfer_policy(self) -> VoteTransferPolicy | None:
        if self.er_policy_name:
            if vtp := self.er_policy.vote_transfer_policy:
                reg = get_vote_transfer_policy_registry()
                if klass := reg.get(vtp):
                    return klass(self)

    def component_enabled(self, name: str, refresh=False) -> bool:
        if not hasattr(self, "_enabled_components") or refresh:
            self._enabled_components = set(
                self.components.filter(enabled=True).values_list(
                    "component_name", flat=True
                )
            )
        return name in self._enabled_components

    def make_upcoming(self, user):
        self.sm.send("make_upcoming", user=user)

    def make_ongoing(self, user):
        self.sm.send("make_ongoing", user=user)

    def close(self, user):
        self.sm.send("close", user=user)

    def request_archiving(self, user):
        self.sm.send("request_archiving", user=user)

    def abort_archiving(self, user):
        self.sm.send("abort_archiving", user=user)

    def request_delete(self, user):
        self.sm.send("request_delete", user=user)

    def abort_delete(self, user):
        self.sm.send("abort_delete", user=user)

    @ensure_atomic
    def archive(self):
        from voteit.meeting.signals import archive_meeting  # Avoid circular import

        self.state = MeetingStateMachine.archived.value
        archive_meeting.send(sender=self.__class__, meeting=self)

    @property
    def is_upcoming(self):
        return self.state == MeetingStateMachine.upcoming.value

    @property
    def is_ongoing(self):
        return self.state == MeetingStateMachine.ongoing.value

    @property
    def is_archived(self):
        return self.state in MeetingStateMachine.archived_states

    @property
    def meeting(self) -> Meeting:
        """
        To fulfill the MeetingContext ABC.
        """
        return self

    def save(self, **kwargs):
        send_er_changed = (
            bool(self.pk)
            and self.er_policy_name
            and self._er_policy_name != self.er_policy_name
        )
        super().save(**kwargs)
        if send_er_changed:
            self.signal_er_policy_changed()

    class QuerySet(models.QuerySet):
        def for_user(self, user: User):
            if user.organisation_id is None:
                return self.none()
            elif user.is_superuser or user.has_perm(
                user.organisation.get_perm(PERM.MANAGE), user.organisation
            ):
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
    organisation_id: int
    groups: models.QuerySet
    invites: models.QuerySet
    electoral_registers: models.QuerySet
    agenda_items: models.QuerySet
    last_read_set: models.QuerySet
    pn_system: PNSystem | None
    presence_checks: PresenceCheck.Manager
    polls: models.QuerySet
    reaction_buttons: models.QuerySet
    speaker_systems: models.QuerySet[SpeakerListSystem]
    components: models.QuerySet[MeetingComponent]
    roles: models.QuerySet[MeetingRoles]
    group_roles: models.QuerySet[GroupRole]
    active_users: models.QuerySet[ActiveUser]
    rooms: models.QuerySet[Room]
    participant_tags: models.QuerySet[ParticipantTags]
    vote_transfers: models.QuerySet[VoteTransfer]


@history_log("meeting__organisation")
@auditlog.register(
    include_fields=[
        "title",
        "body",
        "groupid",
        "meeting",
        "votes",
        "delegate_to",
        "show_on_speaker",
        "post_as",
    ],
)
class MeetingGroup(BaseContent, MeetingContext):
    """
    A named delegation or faction within a meeting (e.g. a political party or union branch).

    Groups can hold collective voting power (``votes``) and delegate it to another
    group (``delegate_to``). Self-delegation and circular chains are prevented by
    a DB constraint and serializer validation respectively.

    Members are linked through ``GroupMembership``. When ``group_votes_active`` is
    on for the meeting, each member's ``GroupMembership.votes`` represents their
    share of the group's total; adjustments to ``MeetingGroup.votes`` may zero out
    individual allocations that exceed the new total.

    ``groupid`` is a URL-safe slug auto-generated from the title on first save.
    """

    name: str = "meeting_group"
    title: str = models.CharField(max_length=100, default="")
    groupid: str = models.CharField(max_length=100, null=True, blank=True)
    meeting: Meeting = models.ForeignKey(
        "Meeting",
        on_delete=models.CASCADE,
        related_name="groups",
    )
    votes: int | None = models.PositiveIntegerField(blank=True, null=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="meeting_groups",
        through="GroupMembership",
    )
    # We may want validators for this later on
    # The actual effect of this field us up to other parts of voteit, mostly group voting
    delegate_to = models.ForeignKey(
        "self",
        on_delete=models.RESTRICT,  # Must be blanked first!
        blank=True,
        null=True,
        related_name="delegations_from",
    )
    show_on_speaker: bool = models.BooleanField(
        verbose_name="Display group name on speaker entry in speaker lists",
        default=True,
    )
    post_as: bool = models.BooleanField(
        verbose_name="Allow members to post as group",
        default=False,
    )

    def save(self, **kwargs):
        if not self.groupid:
            existing_groupids = self.meeting.groups.all().values_list(
                "groupid", flat=True
            )
            base = groupid = slugify(self.title) or _rnd_role_id()
            for i in range(5):
                if groupid not in existing_groupids:
                    self.groupid = groupid
                    break
                groupid = f"{base}-{i + 1}"
        if not self.title:
            self.title = self.groupid
        super().save(**kwargs)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("groupid", "meeting"), name="unique_meeting_id"
            ),
            models.CheckConstraint(
                name="prevent_delegate_to_self",
                check=models.Q(delegate_to_id__isnull=True)
                | ~models.Q(pk=models.F("delegate_to_id")),
            ),
            # delegations_from won't work due to db restrictions. FIXME
            # models.CheckConstraint(
            #     name="prevent_delegate_when_receiving",
            #     check=models.Q(
            #         delegations_from__isnull=False, delegate_to__isnull=False
            #     ),
            # ),
        )

    # Type annotations - relations
    proposals: models.QuerySet[Proposal]
    discussions: models.QuerySet[DiscussionPost]
    memberships: models.QuerySet[GroupMembership]
    delegations_from: models.QuerySet[MeetingGroup]
    objects: models.Manager[MeetingGroup]


@auditlog.register(
    include_fields=[
        "title",
        "role_id",
        "meeting",
        "roles",
    ],
)
class GroupRole(MeetingContext):
    """
    Dynamic group roles for a meeting. These can be automatically created from a meeting dialect,
    or created by a meeting moderator.
    """

    name = "group_role"

    title: str = models.CharField(verbose_name="Title", max_length=100)
    role_id: str = models.CharField(
        verbose_name="Role ID, mostly for scripting",
        max_length=100,
        default=_rnd_role_id,
    )
    meeting: Meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="group_roles"
    )
    roles: list[Role] = RolesField(
        max_length=60,
        role_choices=MeetingRoles.valid_roles.values(),
    )
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
                fields=["title", "meeting"], name="unique_role_title_for_meeting"
            ),
            models.UniqueConstraint(
                fields=("role_id", "meeting"), name="unique_role_id_for_meeting"
            ),
        ]
        verbose_name = "Group role"
        verbose_name_plural = "Group roles"

    def save(self, **kwargs):
        if self.role_id is None:
            if self.title:
                role_id = slugify(self.title)
            else:
                role_id = _rnd_role_id()
            if self.meeting.group_roles.filter(role_id=role_id).exists():
                # We don't care about more checks than this
                role_id = role_id + "-" + "".join(sample(ascii_lowercase, 2))
            self.role_id = role_id
        if not self.title:
            self.title = self.role_id
        super().save(**kwargs)

    def __str__(self):
        return self.title

    # Annotations
    objects: models.Manager[GroupRole]


@auditlog.register(
    include_fields=[
        "user",
        "meeting_group",
        "role",
        "votes",
    ],
)
class GroupMembership(RulesModelMixin, MeetingContext):
    """
    Through-model linking a ``User`` to a ``MeetingGroup``, with an optional ``GroupRole``.

    ``votes`` reflects the vote weight this member will receive in the next electoral
    register update — it is *not* live voting power. It should never exceed the group's
    total ``MeetingGroup.votes``.

    Saving or deleting a membership fires ``group_role_added`` / ``group_role_removed``
    signals which cascade into adding or removing the corresponding meeting-level roles on
    ``MeetingRoles``. Note: using ``.members.add()`` / ``.members.remove()`` on the group
    bypasses through-model signals — ``signals.py`` compensates via ``m2m_changed``.
    """

    name = "group_membership"

    # FIXME: Make sure user's part of the same org as meeting group. Possibly check role too.

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    meeting_group: MeetingGroup = models.ForeignKey(
        MeetingGroup, on_delete=models.CASCADE, related_name="memberships"
    )
    # We won't support keeping membership and deleting a role for now,
    # it will have a lot of side effects we don't want to handle now.
    role: GroupRole | None = models.ForeignKey(
        GroupRole, on_delete=models.SET_NULL, related_name="+", null=True, blank=True
    )
    # Note that this field isn't the actual votes,
    # but the votes we expect the user to have next time the electoral register is updated!
    # The number of assigned votes here should always match the MeetingGroups votes
    votes: int | None = models.PositiveIntegerField(
        verbose_name="Vote weight delegated", null=True, blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "meeting_group"], name="unique_user_in_meeting_group"
            ),
        ]
        verbose_name = "Group membership"
        verbose_name_plural = "Group memberships"

    @property
    def meeting(self) -> Meeting:
        return self.meeting_group.meeting

    def signal_role_added(self):
        from voteit.meeting.signals import group_role_added

        group_role_added.send(
            sender=self.__class__,
            instance=self,
            role=self.role,
        )

    def signal_role_removed(self, role=None):
        from voteit.meeting.signals import group_role_removed

        if role is None:
            role = self.role
        group_role_removed.send(
            sender=self.__class__,
            instance=self,
            role=role,
        )

    # Annotations
    objects: models.Manager[GroupMembership]
    user_id: int
    role_id: int | None
    meeting_group_id: int

    def __str__(self):
        return f"{self.user} in {self.meeting_group.groupid} pk:{self.pk}"
