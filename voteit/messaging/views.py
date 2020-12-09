from django.shortcuts import render
from voteit.messaging.registries import incoming_messages


def echo(request, connection_token):
    return render(request, 'voteit.messaging/echo.html', {
        'connection_token': connection_token,
        'message_types': [x for x in incoming_messages],
    })
