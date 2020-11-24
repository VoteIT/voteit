from django.utils.translation import gettext_lazy as _

from voteit.core.role import Role
from voteit.motion.models import MotionProcessRoles


__all__ = ("ROLE_MP_VIEWER", "ROLE_MP_MOVER", "ROLE_MP_MANAGER")

ROLE_MP_VIEWER = Role("mp_viewer")
ROLE_MP_MOVER = Role("mp_mover")
ROLE_MP_MANAGER = Role("mp_manager")

MotionProcessRoles.add_valid(ROLE_MP_VIEWER, ROLE_MP_MOVER, ROLE_MP_MANAGER)

ROLE_MP_MOVER.add_requirement(ROLE_MP_VIEWER)
ROLE_MP_MANAGER.add_requirement(ROLE_MP_VIEWER)
