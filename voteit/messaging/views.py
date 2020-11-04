from django.shortcuts import render
from voteit.messaging.registries import websocket_incoming_messages


def echo(request, connection_token):
    return render(request, 'voteit.messaging/echo.html', {
        'connection_token': connection_token,
        'message_types': [x for x in websocket_incoming_messages],
    })
