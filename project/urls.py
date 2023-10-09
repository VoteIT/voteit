from django.contrib import admin
from django.urls import include
from django.urls import path

from voteit.core.rest_api.router import router
from voteit.organisation.views import begin_auth
from voteit.organisation.views import finish_auth

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("django-rq/", include("django_rq.urls")),
    path("finish-auth/", finish_auth, name="finish-auth"),
    path("begin-auth/", begin_auth, name="begin-auth"),
]
