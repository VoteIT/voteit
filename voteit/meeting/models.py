from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Generator

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db import transaction
from django.utils import timezone
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django_fsm import FSMField, transition
from voteit.core.abcs import MeetingContext

from voteit.core.models import BaseContent, Roles, RoleContextMixin
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.workflows import MeetingWf

if TYPE_CHECKING:
    from voteit.access_policy.models import AccessPolicy
    from voteit.poll.models import ElectoralRegister


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
    state = FSMField(
        default=MeetingWf.initial, choices=MeetingWf.choices(), editable=False
    )
    start_time = models.DateTimeField(
        verbose_name=_("When the meeting starts/started."), null=True, blank=True
    )
    end_time = models.DateTimeField(
        verbose_name=_("When the meeting ends/ended."), null=True, blank=True
    )
    public = models.BooleanField(
        verbose_name=_("Is this meeting viewable by anyone?"), default=False
    )
    er_policy_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, editable=False
    )
    er_policy_id = models.PositiveIntegerField(null=True, editable=False)
    er_policy = GenericForeignKey("er_policy_type", "er_policy_id")
    organisation = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="meetings",
    )
    archive_after = models.DateTimeField(null=True, editable=False)

    roles_cls = MeetingRoles
    participants = models.ManyToManyField(UserModel, through=MeetingRoles)

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
        with transaction.atomic():
            for ai in self.agenda_items.all():
                ai.archive()
                ai.save()
        # Catch DatabaseError?
        # FIXME cleanup, actual work etc...

    def archiving_allowed(self):
        pass

    @property
    def meeting(self) -> Meeting:
        """ To fullfill the MeetingContext ABC."""
        return self
