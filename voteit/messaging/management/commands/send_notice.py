"""Say something to connected clients, without disconnecting anyone."""

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from voteit.core.messages.notice import NOTICE_TYPES
from voteit.core.messages.notice import Notice
from voteit.organisation.channels import broadcast_organisation
from voteit.organisation.models import Organisation


class Command(BaseCommand):
    help = (
        "Send an s.msg to connected clients, optionally only to one "
        "organisation's. Nothing is disconnected and nobody is logged out."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--message",
            required=True,
            help="Shown to the user as-is. Not translated -- write it in the "
            "language your users read.",
        )
        parser.add_argument(
            "--type",
            default="info",
            choices=NOTICE_TYPES,
            help="Kind of message (default info).",
        )
        parser.add_argument(
            "--organisation",
            type=int,
            help="Organisation pk. Without it, every organisation is reached.",
        )

    def handle(self, *args, **options):
        organisation = options["organisation"]
        if (
            organisation is not None
            and not Organisation.objects.filter(pk=organisation).exists()
        ):
            # Better than silently publishing to a group nobody is in, which is
            # what a wrong pk would otherwise look like: success, no effect.
            raise CommandError(f"No organisation with pk {organisation}")
        notice = Notice(
            payload={"type": options["type"], "message": options["message"]}
        )
        pks = broadcast_organisation(notice, organisation, on_commit=False)
        self.stdout.write(
            self.style.SUCCESS(f"Sent to {len(pks)} organisation channel(s).")
        )
