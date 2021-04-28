from django.shortcuts import render
from voteit.messaging.registries import incoming_messages
from voteit.messaging.registries import outgoing_messages


def echo(request):
    return render(
        request,
        "voteit.messaging/echo.html",
        {
            "message_types": [x for x in incoming_messages],
        },
    )


def message_list(request):
    # FIXME: Not working
    return render(
        request,
        "voteit.messaging/message_list.html",
        {"incoming_messages": [x for x in incoming_messages.values()]},
    )


def message_show(request, msg_type: str, name: str):
    render(
        request,
        "voteit.messaging/message_browser.html",
        {},
    )
