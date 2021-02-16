from voteit.core.registries import permissions


class MotionProcessPermissions:
    MANAGE = permissions.create(
        "voteit.motion.manage_motionprocess", "motion.MotionProcess"
    )
    ADD = permissions.create(
        "voteit.motion.add_motionprocess", "organisation.Organisation"
    )
    CHANGE = permissions.create(
        "voteit.motion.change_motionprocess", "motion.MotionProcess"
    )
    DELETE = permissions.create(
        "voteit.motion.delete_motionprocess", "motion.MotionProcess"
    )
    VIEW = permissions.create(
        "voteit.motion.view_motionprocess", "motion.MotionProcess"
    )


class MotionPermissions:
    ADD = permissions.create("voteit.motion.add_motion", "motion.MotionProcess")
    CHANGE = permissions.create("voteit.motion.change_motion", "motion.Motion")
    VIEW = permissions.create("voteit.motion.view_motion", "motion.Motion")
    DELETE = permissions.create("voteit.motion.delete_motion", "motion.Motion")
    MANAGE = permissions.create("voteit.motion.manage_motion", "motion.Motion")
    SUBMIT = permissions.create("voteit.motion.submit_motion", "motion.Motion")
    RETRACT = permissions.create("voteit.motion.retract_motion", "motion.Motion")
