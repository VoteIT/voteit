from __future__ import annotations

import rules
from django.contrib.auth.models import AbstractUser

from voteit.core.rules import is_author
from voteit.motion.permissions import MotionPermissions
from voteit.motion.permissions import MotionProcessPermissions
from voteit.motion.workflows import MotionProcessWf
from voteit.motion.workflows import MotionWf
from voteit.motion.models import MotionProcess
from voteit.motion.models import Motion
from voteit.organisation.models import Organisation
from voteit.organisation.permissions import OrgPermissions


@rules.predicate
def is_mp_viewer(user: AbstractUser, motion_process: MotionProcess):
    """ User can view the process. """
    return (
        isinstance(motion_process, MotionProcess)
        and motion_process.viewer.filter(pk=user.pk).exists()
    )


@rules.predicate
def is_mp_mover(user: AbstractUser, motion_process: MotionProcess):
    """ Someone who's has the role that enables them to submit motions.
    """
    return (
        isinstance(motion_process, MotionProcess)
        and motion_process.movers.filter(pk=user.pk).exists()
    )


@rules.predicate
def is_mp_manager(user: AbstractUser, motion_process: MotionProcess):
    return (
        isinstance(motion_process, MotionProcess)
        and motion_process.managers.filter(pk=user.pk).exists()
    )


# MotionProcess permissions
@rules.predicate
def can_add_motion_process(user: AbstractUser, organisation: Organisation):
    return user.has_perm(OrgPermissions.MANAGE, organisation)


@rules.predicate
def can_view_motion_process(user: AbstractUser, motion_process: MotionProcess):
    return motion_process.public or is_mp_viewer(user, motion_process)


rules.add_perm(MotionProcessPermissions.MANAGE, is_mp_manager)
rules.add_perm(MotionProcessPermissions.ADD, can_add_motion_process)
rules.add_perm(MotionProcessPermissions.VIEW, can_view_motion_process)
rules.add_perm(MotionProcessPermissions.CHANGE, is_mp_manager)
rules.add_perm(MotionProcessPermissions.DELETE, is_mp_manager)


# Motion permissions
@rules.predicate
def can_add_motion(user: AbstractUser, motion_process: MotionProcess):
    """ Is it possible for the current user to create a motion within this motionprocess?
    """
    if isinstance(motion_process, MotionProcess):
        return (
            is_mp_manager(user, motion_process)
            or motion_process.state == MotionProcessWf.OPEN
            and is_mp_mover(user, motion_process)
        )


@rules.predicate
def can_change_motion(user: AbstractUser, motion: Motion):
    """ Change the text, add proposals etc.
    """
    return is_mp_manager(user, motion.motion_process) or (
        motion.author == user
        and motion.state == MotionWf.DRAFT
        and motion.motion_process.state == MotionProcessWf.OPEN
    )


@rules.predicate
def can_view_motion(user: AbstractUser, motion: Motion):
    """ Motions can always be viewed by their author and managers.
        Other users may view motions in the state published, accepted or rejected if any of these are true:
        - The motion process is public
        - They're listed as viewers or movers
    """
    if is_author(user, motion):
        return True
    if is_mp_manager(user, motion.motion_process):
        return True
    if motion.state in (MotionWf.PUBLISHED, MotionWf.ACCEPTED, MotionWf.REJECTED):
        return motion.motion_process.public or is_mp_viewer(user, motion.motion_process)


@rules.predicate
def can_submit_motion(user: AbstractUser, motion: Motion):
    """ Is the author of the motion able to submit it?
    """
    return (
        is_author(user, motion)
        and motion.state == MotionWf.DRAFT
        and motion.motion_process.state == MotionProcessWf.OPEN
    )


@rules.predicate
def can_retract_motion(user: AbstractUser, motion: Motion):
    """ Is the author of the motion able to submit it?
    """
    return (
        motion.state in (MotionWf.DRAFT, MotionWf.PUBLISHED)
        and is_author(user, motion)
        and motion.motion_process.state == MotionProcessWf.OPEN
    )


@rules.predicate
def can_manage_motion(user: AbstractUser, motion: Motion):
    return is_mp_manager(user, motion.motion_process)


rules.add_perm(MotionPermissions.ADD, can_add_motion)  # Note, related to context here
rules.add_perm(MotionPermissions.CHANGE, can_change_motion)
rules.add_perm(MotionPermissions.VIEW, can_view_motion)
rules.add_perm(MotionPermissions.DELETE, can_manage_motion)
rules.add_perm(MotionPermissions.MANAGE, can_manage_motion)
rules.add_perm(MotionPermissions.SUBMIT, can_submit_motion)
rules.add_perm(MotionPermissions.RETRACT, can_retract_motion | can_manage_motion)
