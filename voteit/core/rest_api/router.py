from rest_framework import routers


router = routers.DefaultRouter()


def register(prefix: str, basename: str = None):
    """
    Decorator to register a ViewSet in project default router.
    """
    assert basename is None or isinstance(basename, str), (
        "Basename must be a string, if supplied"
    )

    def wrapper(viewset):
        router.register(prefix, viewset, basename=basename)

    return wrapper
