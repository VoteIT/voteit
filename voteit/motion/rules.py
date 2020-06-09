import rules
from django.contrib.auth.models import User
from voteit.motion.models import MotionProcess
from voteit.motion.workflows import MotionProcessWf


@rules.predicate
def is_mp_participant(user: User, motion_process: MotionProcess):
    return motion_process.participants.filter(pk=user.pk).exists()


@rules.predicate
def is_mp_mover(user: User, motion_process: MotionProcess):
    return motion_process.movers.filter(pk=user.pk).exists()


@rules.predicate
def is_mp_manager(user: User, motion_process: MotionProcess):
    return motion_process.managers.filter(pk=user.pk).exists()


# FIXME: Detailed rules for states etc
