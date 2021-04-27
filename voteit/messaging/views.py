from django.shortcuts import render
from voteit.messaging.registries import incoming_messages


def echo(request):
    return render(
        request,
        "voteit.messaging/echo.html",
        {
            "message_types": [x for x in incoming_messages],
        },
    )
