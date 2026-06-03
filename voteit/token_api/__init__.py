from rest_framework import routers
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.renderers import JSONRenderer


router = routers.DefaultRouter(root_renderers=[JSONRenderer, BrowsableAPIRenderer])


def register_meeting_api(prefix: str, basename: str | None = None):
    """
    Decorator to register a ViewSet with the token_api router.
    Enforces that the viewset inherits from MeetingApiBaseViewSet.
    """
    if not basename:
        basename = prefix

    def wrapper(viewset):
        from voteit.token_api.base import MeetingApiBaseViewSet

        assert issubclass(viewset, MeetingApiBaseViewSet), (
            f"{viewset.__name__} must inherit from MeetingApiBaseViewSet"
        )
        router.register(prefix, viewset, basename=basename)
        return viewset

    return wrapper
