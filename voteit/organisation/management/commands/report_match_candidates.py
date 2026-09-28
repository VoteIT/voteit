from __future__ import annotations

from collections import Counter

from django.core.management import BaseCommand

from voteit.core.user_merger import user_activity_score
from voteit.organisation.matching import is_elevated
from voteit.organisation.matching import normalise
from voteit.organisation.matching import user_match_key
from voteit.organisation.models import Organisation


class Command(BaseCommand):
    """
    Measure what the account matcher would do, before letting it do anything.

    The number that matters is how many accounts share an
    (email, first name, last name) triple with another account: that is the rate
    at which the matcher will refuse to decide and hand the person to the ask
    path instead. If it is high, the matcher is the wrong shape.
    """

    help = "Report how well existing accounts could be matched by email and name."

    def add_arguments(self, parser):
        parser.add_argument(
            "--host",
            help="Limit to one organisation, by hostname. Default: every one.",
        )
        parser.add_argument(
            "--provider",
            default="scoutid",
            help="The login method being rolled out. Accounts already holding "
            "one of these are not candidates for it.",
        )
        parser.add_argument(
            "--show-ambiguous",
            action="store_true",
            help="List the colliding triples, masked, so they can be chased up.",
        )

    def handle(self, *args, **options):
        organisations = Organisation.objects.all()
        if host := options["host"]:
            organisations = organisations.filter(host=host)
            if not organisations:
                self.stderr.write(self.style.ERROR(f"No organisation on {host}"))
                return
        for organisation in organisations.order_by("host"):
            self.report(organisation, options)

    def report(self, organisation: Organisation, options):
        provider = options["provider"]
        users = list(
            organisation.users.filter(is_active=True)
            .exclude(social_auth__provider=provider)
            .prefetch_related("organisation_roles")
        )
        # The address is what reaches an account at all. The name only decides
        # whether the person has to be asked about it.
        addresses = Counter(normalise(user.email) for user in users if user.email)
        identities = Counter(key for user in users if (key := user_match_key(user)))
        shared = {key for key, count in identities.items() if count > 1}

        # Every reachable account lands in exactly one of the buckets below, in
        # the order the matcher decides them.
        reachable = [user for user in users if user.email]
        elevated = [user for user in reachable if is_elevated(user)]
        rest = [user for user in reachable if not is_elevated(user)]
        no_name = [user for user in rest if not user_match_key(user)]
        named = [user for user in rest if user_match_key(user)]
        ambiguous = [user for user in named if user_match_key(user) in shared]
        alone = [user for user in named if user_match_key(user) not in shared]
        stale = [user for user in alone if user.last_login is None]
        auto = [user for user in alone if user.last_login is not None]

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n{organisation.title or organisation.pk} ({organisation.host})"
            )
        )
        self.line(f"Active accounts without {provider}", len(users))
        self.line("  reachable at an address", len(reachable))
        self.line("  unreachable, no address", len(users) - len(reachable))
        self.stdout.write("")
        self.line("Would link silently", len(auto))
        self.line("Offered, never logged in", len(stale))
        self.line(
            "Offered, shared identity",
            len(ambiguous),
            f"{len(shared)} share a name and address",
        )
        self.line("Offered, no full name", len(no_name))
        self.line("Needs the other login", len(elevated), "org roles or staff")
        self.stdout.write("")
        self.line(
            "Addresses under more than one name",
            sum(1 for _email, count in addresses.items() if count > 1),
            "each offers the others too",
        )
        if auto:
            risky = [user for user in auto if user_activity_score(user) == 0]
            self.line("Linked accounts holding nothing yet", len(risky))
        if options["show_ambiguous"] and shared:
            self.stdout.write("\n  Shared identities:")
            for email, first, last in sorted(shared):
                count = identities[(email, first, last)]
                self.stdout.write(f"    {email}  {first} {last}  x{count}")

    def line(self, label: str, value: int, note: str = ""):
        note = f"  ({note})" if note else ""
        self.stdout.write(f"  {label:.<44} {value:>6}{note}")
