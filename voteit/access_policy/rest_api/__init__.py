from voteit.core.rest_api import router

from . import views


router.register(
    "access-policies", views.AccessPoliciesViewSet, basename="access-policies"
)
router.register(
    "meeting-invites", views.MeetingInviteViewSet, basename="meeting-invites"
)
router.register(
    "matched-invites", views.UserMatchedInviteViewSet, basename="matched-invites"
)
