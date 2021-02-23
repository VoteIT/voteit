from voteit.core.registries import permissions


class MotionProcessPermissions:
    """
    The permissions must map the object permissions in django.

    >>> from voteit.core.testing import find_bad_permission_names
    >>> from voteit.motion.models import MotionProcess
    >>> find_bad_permission_names(MotionProcessPermissions, MotionProcess)

    """

    MANAGE = permissions.create("motion.manage_motionprocess", "motion.MotionProcess")
    ADD = permissions.create("motion.add_motionprocess", "organisation.Organisation")
    CHANGE = permissions.create("motion.change_motionprocess", "motion.MotionProcess")
    DELETE = permissions.create("motion.delete_motionprocess", "motion.MotionProcess")
    VIEW = permissions.create("motion.view_motionprocess", "motion.MotionProcess")


class MotionPermissions:
    """
    The permissions must map the object permissions in django.

    >>> from voteit.core.testing import find_bad_permission_names
    >>> from voteit.motion.models import Motion
    >>> find_bad_permission_names(MotionPermissions, Motion)

    """

    ADD = permissions.create("motion.add_motion", "motion.MotionProcess")
    CHANGE = permissions.create("motion.change_motion", "motion.Motion")
    VIEW = permissions.create("motion.view_motion", "motion.Motion")
    DELETE = permissions.create("motion.delete_motion", "motion.Motion")
    MANAGE = permissions.create("motion.manage_motion", "motion.Motion")
    SUBMIT = permissions.create("motion.submit_motion", "motion.Motion")
    RETRACT = permissions.create("motion.retract_motion", "motion.Motion")
