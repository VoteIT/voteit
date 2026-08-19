"""
ASGI config for the voteit project.

Serves HTTP through Django and websockets through chanx/Channels.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings_development")

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter
from chanx.channels.routing import include
from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(include("project.routing_ws")),
    }
)
