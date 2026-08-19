from channels.routing import URLRouter
from chanx.channels.routing import include
from chanx.channels.routing import re_path

router = URLRouter([re_path("ws/", include("voteit.messaging.routing"))])
