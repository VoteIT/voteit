from voteit.core.rest_api import router

from . import views


router.register(
    "access-policies", views.AccessPoliciesViewSet, basename="access-policies"
)
