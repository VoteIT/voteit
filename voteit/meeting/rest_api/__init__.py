from voteit.core.rest_api import router

from .views import *

router.register(
    'meetings', MeetingViewSet,
    basename='meeting'
)
