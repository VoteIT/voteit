from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/(?P<connection_token>\w+)/$', consumers.WebsocketDemuxConsumer.as_asgi()),
]
