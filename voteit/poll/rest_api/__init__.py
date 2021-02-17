from voteit.core.rest_api import router

from .views import *

router.register('polls', PollViewSet)
router.register('electoral-registers', ElectoralRegisterViewSet)
