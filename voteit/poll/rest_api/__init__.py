from voteit.core.rest_api import router

from .views import PollViewSet

router.register('polls', PollViewSet)
