from django.contrib.auth.models import User
from django.db import models
from django_fsm import FSMField
from django_fsm import transition

from voteit.core.models import BaseContent
from voteit.motion.workflows import MotionProcessWf
from voteit.motion.workflows import MotionWf


class MotionProcess(BaseContent):
    state = FSMField(
        default=MotionProcessWf.initial, choices=MotionProcessWf.choices(), protected=True
    )
    organisation = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="motion_processes",
    )
    participants = models.ManyToManyField(
        User, blank=True, related_name="participant_in_motionprocesses"
    )
    movers = models.ManyToManyField(
        User, blank=True, related_name="mover_in_motionprocesses"
    )
    managers = models.ManyToManyField(
        User, blank=True, related_name="manager_in_motionprocesses"
    )

    @transition(field=state, target=MotionProcessWf.PRIVATE)
    def private(self):
        pass

    @transition(field=state, target=MotionProcessWf.OPEN)
    def open(self):
        pass

    @transition(field=state, target=MotionProcessWf.CLOSED)
    def close(self):
        pass


class Motion(BaseContent):
    state = FSMField(
        default=MotionWf.initial, choices=MotionWf.choices(), protected=True
    )
    motion_process = models.ForeignKey(MotionProcess, on_delete=models.CASCADE, related_name="motions")
    body = models.TextField()
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="motions")


class MotionProposal(models.Model):
    """ Lightweight version of the proposal model. This is only used within the context of the motion.
        It's used as a template to create a motion later on.
    """
    motion = models.ForeignKey(Motion, on_delete=models.CASCADE, related_name="proposals")
    text = models.TextField()
