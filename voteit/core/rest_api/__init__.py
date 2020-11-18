from django.conf import settings
from rest_framework.routers import DefaultRouter

from . import views


router = DefaultRouter()


if settings.DEBUG:
    router.register('dev-login', views.DevLogin)
