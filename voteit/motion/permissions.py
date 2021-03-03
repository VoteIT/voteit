from voteit.core.permission import ModelPermissions
from voteit.core.permission import Permission as P


class MotionProcessPermissions(ModelPermissions):
    model = "motion_process"

    MANAGE = P("motion.manage_motionprocess")
    ADD = P("motion.add_motionprocess", context="organisation")
    CHANGE = P("motion.change_motionprocess")
    DELETE = P("motion.delete_motionprocess")
    VIEW = P("motion.view_motionprocess")


class MotionPermissions(ModelPermissions):
    model = "motion"

    ADD = P("motion.add_motion", context="motion_process")
    CHANGE = P("motion.change_motion")
    VIEW = P("motion.view_motion")
    DELETE = P("motion.delete_motion")
    MANAGE = P("motion.manage_motion")
    SUBMIT = P("motion.submit_motion")
    RETRACT = P("motion.retract_motion")
