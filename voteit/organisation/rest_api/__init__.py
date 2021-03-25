from voteit.core.rest_api import router
from voteit.organisation.rest_api import views


router.register("organisations", views.OrganisationViewSet, basename="organisations")
router.register("tos", views.TOSViewSet, basename="tos")
router.register("user_consents", views.UserConsentViewSet, basename="user_consents")
