"""
ASGI config for the voteit project.

Serves HTTP through Django and websockets through chanx/Channels.
"""

import os

# Matches wsgi.py. Falling back to development settings here would mean an ASGI
# server started without DJANGO_SETTINGS_MODULE runs production traffic with
# DEBUG on, ALLOWED_HOSTS ["*"] and /asyncapi/docs/ served publicly. Local dev
# sets this explicitly through .env.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings_production")

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter
from channels.security.websocket import AllowedHostsOriginValidator
from chanx.channels.routing import include
from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # The socket was not origin-checked at all under envelope. Anything not
        # in ALLOWED_HOSTS is now rejected before the handshake completes, so
        # ALLOWED_HOSTS has to cover the SPA's origin.
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(include("project.routing_ws"))
        ),
    }
)
