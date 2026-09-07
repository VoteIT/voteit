"""How many people are connected right now, in total and per organisation.

The same numbers as /admin/voteit_messaging/connection/online/, from the same
code (voteit.messaging.presence) -- handy before running close_sockets, and the
only way to see them without a browser.

Channels never reports a consumer that died with its process, so an open connection only
means someone is there if it has done something lately.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand

from voteit.messaging.presence import presence

DEFAULT_WINDOW_MINUTES = 10


class Command(BaseCommand):
    help = (
        "Count the websocket connections that are currently online, broken "
        "down by organisation."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--window",
            type=int,
            default=DEFAULT_WINDOW_MINUTES,
            metavar="MINUTES",
            help="How recently a socket must have been active to count as "
            f"online (default {DEFAULT_WINDOW_MINUTES}). ",
        )

    def handle(self, *args, **options):
        counted = presence(timedelta(minutes=options["window"]))

        rows = [
            (row.organisation.title, row.users, row.sockets)
            for row in counted.organisations
        ]
        if orphans := counted.users_without_organisation:
            rows.append(("(no organisation)", orphans, 0))

        width = max([len(title) for title, _, _ in rows] + [len("Organisation")])
        self.stdout.write(f"{'Organisation':<{width}}  {'Users':>7}  {'Sockets':>7}")
        self.stdout.write("-" * (width + 18))
        for title, users, sockets in rows:
            self.stdout.write(f"{title:<{width}}  {users:>7}  {sockets:>7}")
        self.stdout.write("-" * (width + 18))
        self.stdout.write(
            self.style.SUCCESS(
                f"{'TOTAL':<{width}}  {counted.users:>7}  {counted.sockets:>7}"
            )
        )
        self.stdout.write(
            f"{counted.sockets_per_user} socket(s) per user, "
            f"active within {options['window']} min."
        )
