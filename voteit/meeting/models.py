from __future__ import annotations

from datetime import timedelta, datetime
from typing import TYPE_CHECKING, Generator, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db import transaction
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django_fsm import FSMField, transition

from voteit.core.abcs import MeetingContext
from voteit.core.models import BaseContent, Roles, RoleContextMixin
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.workflows import MeetingWf
from voteit.poll.utils import get_electoral_policy_registry

if TYPE_CHECKING:
    from voteit.access_policy.models import AccessPolicy
    from voteit.poll.models import ElectoralRegister
    from voteit.poll.abcs import ElectoralRegisterPolicy
    from voteit.organisation.models import Organisation

__all__ = "Meeting", "MeetingRoles"


UserModel = get_user_model()


class MeetingRoles(Roles, MeetingContext):
    """ Contains assigned meeting roles for a specific meeting and user"""

    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meeting_roles"
    )
    context: Meeting = models.ForeignKey(
        "Meeting", on_delete=models.CASCADE, related_name="roles"
    )

    @property
    def meeting(self) -> Meeting:
        return self.context


class Meeting(BaseContent, RoleContextMixin, MeetingContext):
    title: str = models.CharField(max_length=100)
    state: str = FSMField(
        default=MeetingWf.initial, choices=MeetingWf.choices(), editable=False
    )
    start_time: Optional[datetime] = models.DateTimeField(
        verbose_name=_("When the meeting starts/started."), null=True, blank=True
    )
    end_time: Optional[datetime] = models.DateTimeField(
        verbose_name=_("When the meeting ends/ended."), null=True, blank=True
    )
    public: bool = models.BooleanField(
        verbose_name=_("Is this meeting viewable by anyone?"), default=False
    )
    er_policy_name: Optional[str] = models.CharField(
        verbose_name=_("ID of used electoral policy"),
        max_length=30,
        null=True,
        blank=True,
    )
    organisation: Optional[Organisation] = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="meetings",
    )
    archive_after: Optional[datetime] = models.DateTimeField(null=True, editable=False)

    roles_cls = MeetingRoles
    participants = models.ManyToManyField(UserModel, through=MeetingRoles)

    @cached_property
    def er_policy(self) -> ElectoralRegisterPolicy:
        reg = get_electoral_policy_registry()
        return reg[self.er_policy_name](self)

    def get_latest_er(self) -> ElectoralRegister:
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

    @transition(
        field=state,
        source=MeetingWf.ONGOING,
        target=MeetingWf.UPCOMING,
        permission=MeetingPermissions.MODERATE,
    )
    def upcoming(self):
        pass

    @transition(
        field=state,
        source=[MeetingWf.UPCOMING, MeetingWf.CLOSED],
        target=MeetingWf.ONGOING,
        permission=MeetingPermissions.MODERATE,
        conditions=[valid_er_policy_guard],
    )
    def ongoing(self):
        self.start_time = timezone.now()

    @transition(
        field=state,
        source=MeetingWf.ONGOING,
        target=MeetingWf.CLOSED,
        permission=MeetingPermissions.MODERATE,
    )
    def close(self):
        self.end_time = timezone.now()

    @transition(
        field=state,
        source=MeetingWf.CLOSED,
        target=MeetingWf.ARCHIVING,
        permission=MeetingPermissions.ARCHIVE,
    )
    def request_archiving(self):
        self.archive_after = now() + timedelta(days=3)
        # FIXME: Do lots of checks here later on, make sure ais are closed etc

    @transition(
        field=state,
        source=MeetingWf.ARCHIVING,
        target=MeetingWf.CLOSED,
        permission=MeetingPermissions.ARCHIVE,
    )
    def abort_archiving(self):
        self.archive_after = None

    @transition(
        field=state, target=MeetingWf.ARCHIVED, permission="__not_allowed_manually__"
    )
    def archive(self):
        from voteit.meeting.signals import archive_meeting  # Avoid circular import

        with transaction.atomic():
            archive_meeting.send(sender=self.__class__, meeting=self)

    def archiving_allowed(self):
        pass

    @property
    def is_archived(self):
        return self.state in MeetingWf.archived_states

    @property
    def meeting(self) -> Meeting:
        """ To fullfill the MeetingContext ABC."""
        return self

    class QuerySet(models.QuerySet):
        def for_user(self, user: AbstractUser):
            if user.is_superuser:
                return self.all()
            return self.filter(
                models.Q(public=True) | models.Q(participants=user)
            ).distinct()

    class Manager(models.Manager):
        def get_queryset(self):
            return Meeting.QuerySet(self.model, using=self._db)

        def for_user(self, user: AbstractUser):
            return self.get_queryset().for_user(user)

    objects = Manager()
