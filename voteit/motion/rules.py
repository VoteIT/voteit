from __future__ import annotations

import rules
from typing import TYPE_CHECKING
from django.contrib.auth.models import User
from voteit.motion.permissions import MotionPermissions
from voteit.motion.permissions import MotionProcessPermissions
from voteit.motion.workflows import MotionProcessWf
from voteit.motion.workflows import MotionWf

if TYPE_CHECKING:
    from voteit.motion.models import MotionProcess
    from voteit.motion.models import Motion
    from voteit.motion.models import MotionProposal


# Role definitions
@rules.predicate
def is_mp_viewer(user: User, motion_process: MotionProcess):
    """ User can view the process. """
    if motion_process is not None:
        return motion_process.viewer.filter(pk=user.pk).exists()


@rules.predicate
def is_mp_mover(user: User, motion_process: MotionProcess):
    """ Someone who's has the role that enables them to submit motions.
    """
    if motion_process is not None:
        return motion_process.movers.filter(pk=user.pk).exists()


@rules.predicate
def is_mp_manager(user: User, motion_process: MotionProcess):
    if motion_process is not None:
        return motion_process.managers.filter(pk=user.pk).exists()


# MotionProcess permissions
@rules.predicate
def can_add_motion(user: User, motion_process: MotionProcess):
    """ Is it possible for the current user to create a motion within this motionprocess?
    """
    return (
        is_mp_manager(user, motion_process)
        or motion_process.state == MotionProcessWf.OPEN
        and is_mp_mover(user, motion_process)
    )


rules.add_perm(MotionProcessPermissions.MANAGE, is_mp_manager)
rules.add_perm(MotionPermissions.ADD, can_add_motion)  # Note, related to context here


# Motion permissions
@rules.predicate
def can_change_motion(user: User, motion: Motion):
    """ Change the text, add proposals etc.
    """
    return is_mp_manager(user, motion.motion_process) or (
        motion.author == user
        and motion.state == MotionWf.DRAFT
        and motion.motion_process.state == MotionProcessWf.OPEN
    )


@rules.predicate
def can_submit_motion(user: User, motion: Motion):
    """ Is the author of the motion able to submit it?
    """
    return (
        motion.author == user
        and motion.state == MotionWf.DRAFT
        and motion.motion_process.state == MotionProcessWf.OPEN
    )


@rules.predicate
def can_retract_motion(user: User, motion: Motion):
    """ Is the author of the motion able to submit it?
    """
    return (
        motion.state in (MotionWf.DRAFT, MotionWf.PUBLISHED)
        and motion.author == user
        and motion.motion_process.state == MotionProcessWf.OPEN
    )


@rules.predicate
def can_manage_motion(user: User, motion: Motion):
    return is_mp_manager(user, motion.motion_process)


rules.add_perm(MotionPermissions.CHANGE, can_change_motion)
rules.add_perm(MotionPermissions.SUBMIT, can_submit_motion)
rules.add_perm(MotionPermissions.RETRACT, can_retract_motion | can_manage_motion)
rules.add_perm(MotionPermissions.MANAGE, can_manage_motion)
