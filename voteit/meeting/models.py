from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Generator

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db import transaction
from django.utils import timezone
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django_fsm import FSMField, transition

from voteit.access_policy.registries import access_policies
from voteit.core.models import BaseContent
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.workflows import MeetingWf

if TYPE_CHECKING:
    from voteit.access_policy.models import AccessPolicy
    from voteit.poll.models import ElectoralRegister


__all__ = 'Meeting',


class Meeting(BaseContent):
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
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name=_(
            "User can participate in some form. "
            "This is basically read permission, unless the process is public."
        ),
        blank=True,
        related_name="participant_in_meetings",
        editable=False,
    )
    potential_voters = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name=_("This user may become a voter in this meeting."),
        blank=True,
        related_name="potential_voter_in_meetings",
        editable=False,
    )
    discussers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name=_("User may add discussion posts."),
        blank=True,
        related_name="discusser_in_meetings",
        editable=False,
    )
    proposers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name=_("User may add proposals."),
        blank=True,
        related_name="proposer_in_meetings",
        editable=False,
    )
    moderators = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="moderator_in_meetings", editable=False
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

    def get_latest_er(self) -> ElectoralRegister:
        return (
            self.electoral_registers.filter(meeting=self).order_by("-created").first()
        )

    def get_access_policies(self, only_active=True) -> Generator[AccessPolicy]:
        query = {}
        if only_active:
            query["active"] = True
        for ap in access_policies.values():
            qs = ap.objects.filter(meeting=self, **query)
            if qs:
                yield qs.first()  # All of them are 1-1 relations

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
        field=state,
        target=MeetingWf.ARCHIVED,
        permission="__not_allowed_manually__",
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
