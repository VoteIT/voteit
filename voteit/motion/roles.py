from django.utils.translation import gettext_lazy as _

from voteit.core.role import Role, roles
from voteit.motion.models import MotionProcess
from voteit.motion.rules import is_mp_manager
from voteit.motion.rules import is_mp_mover
from voteit.motion.rules import is_mp_viewer

__all__ = ("MPViewer", "MPMover", "MPManager")


@roles
class MPViewer(Role):
    model = MotionProcess
    m2m_field = "viewer"
    title = _("Motion process viewer")
    name = "mp_viewer"


@roles
class MPMover(Role):
    model = MotionProcess
    m2m_field = "movers"
    title = _("Motion process mover")
    name = "mp_participant"


MPMover.add_requirement(MPViewer)


@roles
class MPManager(Role):
    model = MotionProcess
    m2m_field = "managers"
    title = _("Motion process manager")
    name = "mp_manager"


MPManager.add_requirement(MPViewer)
