from voteit.core.rest_api import router

from . import views


router.register(
    "meeting-invites",
    views.MeetingInviteViewSet,
    basename="meeting-invites",
)
router.register(
    "handle-matched-invites",
    views.HandleMatchedInvitesViewSet,
    basename="handle-matched-invites",
)
router.register(
    "used-invites",
    views.UsedInvitesViewSet,
    basename="users-used-invites",
)
router.register(
    "match-invites",
    views.MatchInvitesViewSet,
    basename="match-invites",
)
