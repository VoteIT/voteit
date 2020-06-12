from django.contrib.auth.models import User
from django.db import models
from django_fsm import FSMField
from django_fsm import transition
from django.utils.translation import gettext_lazy as _

from voteit.core.models import BaseContent
from voteit.motion.workflows import MotionProcessWf
from voteit.motion.workflows import MotionWf
from voteit.motion.permissions import MotionProcessPermissions as MPP
from voteit.motion.permissions import MotionPermissions as MP


class MotionProcess(BaseContent):
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
        verbose_name=_("Is anyone allowed to view motions except drafts and retracted?"), default=False
    )
    viewer = models.ManyToManyField(
        User,
        verbose_name=_(
            "In case this process isn't public, add users who should be able to view here"
        ),
        blank=True,
        related_name="viewer_in_motionprocesses",
    )
    movers = models.ManyToManyField(
        User,
        verbose_name=_("Users able to write motions - always able to view too."),
        blank=True,
        related_name="mover_in_motionprocesses",
    )
    managers = models.ManyToManyField(
        User,
        verbose_name=_("Managers for the process"),
        blank=True,
        related_name="manager_in_motionprocesses",
    )

    @transition(field=state, target=MotionProcessWf.OPEN, permission=MPP.MANAGE)
    def open(self):
        pass

    @transition(field=state, target=MotionProcessWf.CLOSED, permission=MPP.MANAGE)
    def close(self):
        pass


class Motion(BaseContent):
    state = FSMField(
        default=MotionWf.initial, choices=MotionWf.choices(), protected=True
    )
    motion_process = models.ForeignKey(
        MotionProcess, on_delete=models.CASCADE, related_name="motions"
    )
    body = models.TextField()
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="motions")

    @transition(
        field=state,
        source=MotionWf.DRAFT,
        target=MotionWf.PUBLISHED,
        permission=MP.SUBMIT,
    )
    def submit(self):
        """ User submits their motion.
        """

    @transition(field=state, target=MotionWf.PUBLISHED, permission=MP.MANAGE)
    def publish(self):
        """ Moderator publishes a motion.
        """

    @transition(
        field=state,
        source=MotionWf.PUBLISHED,
        target=MotionWf.RETRACTED,
        permission=MP.RETRACT,
    )
    def retract(self):
        """ User or moderator retracts the motion.
        """

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
    """ Lightweight version of the proposal model. This is only used within the context of the motion.
        It's used as a template to create a motion later on.
    """

    motion = models.ForeignKey(
        Motion, on_delete=models.CASCADE, related_name="proposals"
    )
    text = models.TextField()
