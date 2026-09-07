"""Close every open websocket, e.g. just before a restart."""

from django.core.management.base import BaseCommand

from voteit.core.messages.notice import NOTICE_TYPES
from voteit.core.messages.notice import Notice
from voteit.messaging.close import close_all_connections
from voteit.messaging.models import GOING_AWAY


class Command(BaseCommand):
    help = (
        "Disconnect every connected client, optionally showing them a message "
        "first. Does not log anyone out. Run online_connections first to see "
        "how many that is."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--message",
            default="",
            help="Sent as an s.msg before the close, to be shown to the user. "
            "Not translated -- write it in the language your users read.",
        )
        parser.add_argument(
            "--type",
            default="warning",
            choices=NOTICE_TYPES,
            help="Kind of message, when --message is given (default warning).",
        )
        parser.add_argument(
            "--code",
            type=int,
            default=GOING_AWAY,
            help=f"Websocket close code (default {GOING_AWAY}, going away, "
            "which tells the client to come back). Use 1000 to say stay out. "
            "Both count as a normal closure in the socket stats.",
        )

    def handle(self, *args, **options):
        notice = None
        if options["message"]:
            notice = Notice(
                payload={"type": options["type"], "message": options["message"]}
            )
        names = close_all_connections(code=options["code"], notice=notice)
        self.stdout.write(self.style.SUCCESS(f"Asked {len(names)} socket(s) to close."))
