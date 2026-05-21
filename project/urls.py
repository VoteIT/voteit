from controlcenter.views import controlcenter
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include
from django.urls import path

from voteit.core.rest_api.router import router
from voteit.token_api import router as token_router

urlpatterns = [
    path("admin/dashboard/", controlcenter.urls),
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("token-api/", include(token_router.urls)),
    path("django-rq/", include("django_rq.urls")),
    path("", include("social_django.urls")),
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
