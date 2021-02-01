from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django_fsm import FSMField
from django_fsm import transition
from django.utils.translation import gettext_lazy as _
from typing import List

from voteit.core.models import BaseContent, Roles, RoleContextMixin
from voteit.meeting.models import Meeting
from voteit.motion.workflows import MotionProcessWf
from voteit.motion.workflows import MotionWf
from voteit.motion.permissions import MotionProcessPermissions as MPP
from voteit.motion.permissions import MotionPermissions as MP


class MotionProcessRoles(Roles):
    """ Contains assigned meeting roles for a specific meeting and user"""

    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="motion_process_roles",
    )
    context: MotionProcess = models.ForeignKey(
        "MotionProcess", on_delete=models.CASCADE, related_name="roles"
    )


class MotionProcess(BaseContent, RoleContextMixin):
    title: str = models.CharField(max_length=100)
    state = FSMField(
        default=MotionProcessWf.initial,
        choices=MotionProcessWf.choices(),
        protected=True,
    )
    organisation = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="motion_processes",
    )
    public = models.BooleanField(
        verbose_name=_(
            "Is anyone allowed to view motions except drafts and retracted?"
        ),
        default=False,
    )

    roles_cls = MotionProcessRoles

    @transition(field=state, target=MotionProcessWf.OPEN, permission=MPP.MANAGE)
    def open(self):
        pass

    @transition(field=state, target=MotionProcessWf.CLOSED, permission=MPP.MANAGE)
    def close(self):
        pass

    def get_selected_motions_qs(self, states: List[str] = None) -> models.QuerySet:
        if states is None:
            states = [MotionWf.ACCEPTED]
        return self.motions.filter(state__in=states).order_by("created")

    def populate_meeting(self, meeting: Meeting, states: List[str] = None):
        """ Populate a meeting from given states. """
        # FIXME: Sorted, created etc
        # FIXME: Override author...?
        # FIXME: Body fields, richtext etc?
        qs = self.get_selected_motions_qs(states)
        for motion in qs.all().prefetch_related("author", "proposals"):
            ai = meeting.agenda_items.create(
                author=motion.author, title=motion.title, body=motion.body
            )
            # FIXME: ordering!
            for prop in motion.proposals.all():
                ai.proposals.create(author=motion.author, body=prop.body)


class Motion(BaseContent):
    title: str = models.CharField(max_length=100)

    state = FSMField(
        default=MotionWf.initial, choices=MotionWf.choices(), protected=True
    )
    motion_process = models.ForeignKey(
        MotionProcess, on_delete=models.CASCADE, related_name="motions"
    )
    body = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="motions"
    )

    @transition(
        field=state,
        source=MotionWf.DRAFT,
        target=MotionWf.PUBLISHED,
        permission=MP.SUBMIT,
    )
    def submit(self):
        """User submits their motion."""

    @transition(field=state, target=MotionWf.PUBLISHED, permission=MP.MANAGE)
    def publish(self):
        """Moderator publishes a motion."""

    @transition(
        field=state,
        source=MotionWf.PUBLISHED,
        target=MotionWf.RETRACTED,
        permission=MP.RETRACT,
    )
    def retract(self):
        """User or moderator retracts the motion."""

    @transition(
        field=state,
        source=MotionWf.PUBLISHED,
        target=MotionWf.ACCEPTED,
        permission=MP.MANAGE,
    )
    def accept(self):
        pass

    @transition(
        field=state,
        source=MotionWf.PUBLISHED,
        target=MotionWf.REJECTED,
        permission=MP.MANAGE,
    )
    def reject(self):
        pass

    @transition(
        field=state,
        source=MotionWf.PUBLISHED,
        target=MotionWf.UNHANDLED,
        permission=MP.MANAGE,
    )
    def unhandled(self):
        pass

    @transition(
        field=state,
        source=MotionWf.PUBLISHED,
        target=MotionWf.DRAFT,
        permission=MP.MANAGE,
    )
    def draft(self):
        pass


class MotionProposal(models.Model):
    """Lightweight version of the proposal model. This is only used within the context of the motion.
    It's used as a template to create a motion later on.
    """

    motion = models.ForeignKey(
        Motion, on_delete=models.CASCADE, related_name="proposals"
    )
    body = models.TextField()
    # FIXME: We might want to fix ordering here
