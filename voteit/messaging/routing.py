from channels.routing import URLRouter
from chanx.channels.routing import path

from voteit.messaging.consumer import VoteitConsumer

# chanx's include() looks for a module-level name "router".
router = URLRouter([path("", VoteitConsumer.as_asgi())])
