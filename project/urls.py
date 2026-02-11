from controlcenter.views import controlcenter
from django.contrib import admin
from django.urls import include
from django.urls import path

from voteit.core.rest_api.router import router

urlpatterns = [
    path("admin/dashboard/", controlcenter.urls),
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("django-rq/", include("django_rq.urls")),
    path("", include("social_django.urls")),
]
