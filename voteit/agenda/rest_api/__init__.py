from voteit.core.rest_api import router

from . import views


router.register(
    "agenda-items",
    views.AgendaViewSet,
)
