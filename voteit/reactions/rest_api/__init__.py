from voteit.core.rest_api import router
from voteit.reactions.rest_api.views import ReactionButtonViewSet

router.register("reaction-buttons", ReactionButtonViewSet, basename="reaction-buttons")
