from voteit.core.rest_api import router

from .views import *

router.register("meetings", MeetingViewSet, basename="meeting")
router.register("meeting-roles", MeetingRolesViewSet, basename="meeting-roles")
router.register("meeting-groups", MeetingGroupViewSet, basename="meeting-groups")
