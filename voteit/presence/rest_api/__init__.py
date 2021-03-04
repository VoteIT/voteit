from voteit.core.rest_api import router
from voteit.presence.rest_api.views import PresenceCheckViewSet
from voteit.presence.rest_api.views import PresenceSystemViewSet

router.register("presence-systems", PresenceSystemViewSet, basename="presence-systems")
router.register("presence-checks", PresenceCheckViewSet, basename="presence-checks")
