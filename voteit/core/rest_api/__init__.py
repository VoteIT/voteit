from rest_framework.routers import DefaultRouter

from . import views


router = DefaultRouter()

router.register("users", views.UserSearchViewSet, "users")
router.register("user", views.UserView, "user")
