import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils.timezone import now

from voteit.app.scouterna import SCOUTID_PROVIDER
from voteit.organisation.models import Organisation
from voteit.organisation.roles import ROLE_ORG_MANAGER

LINE = re.compile(r"^\s*(\S[^.]*?)\.+\s+(\d+)(?:\s+\((.*)\))?$", re.M)


class ReportMatchCandidatesTests(TestCase):
    """
    The report has to count the same way the matcher decides, or it measures
    nothing worth knowing.
    """

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(title="Scouts", host="scouts.example")

    def _user(self, username, **kwargs):
        kwargs.setdefault("first_name", "Kim")
        kwargs.setdefault("last_name", "Scout")
        kwargs.setdefault("email", f"{username}@example.com")
        kwargs.setdefault("last_login", now())
        return self.org.users.create(username=username, **kwargs)

    def _run(self, **options):
        out = StringIO()
        call_command(
            "report_match_candidates", host=self.org.host, stdout=out, **options
        )
        return out.getvalue()

    def _counts(self, **options) -> dict[str, tuple[int, str]]:
        """
        {label: (count, note)}. The dot padding is cosmetic, don't assert on it.
        """
        found = {}
        for label, value, note in LINE.findall(self._run(**options)):
            found.setdefault(label.strip(), (int(value), note or ""))
        return found

    def test_a_plain_account_would_link(self):
        self._user("kim")
        self.assertEqual((1, ""), self._counts()["Would link silently"])

    def test_half_a_name_is_offered_rather_than_linked(self):
        self._user("kim", last_name="")
        counts = self._counts()
        self.assertEqual((1, ""), counts["Offered, no full name"])
        self.assertEqual((0, ""), counts["Would link silently"])

    def test_a_shared_identity_is_ambiguous(self):
        self._user("kim", email="shared@example.com")
        self._user("kim2", email="shared@example.com")
        counts = self._counts()
        self.assertEqual(
            (2, "1 share a name and address"), counts["Offered, shared identity"]
        )
        self.assertEqual((0, ""), counts["Would link silently"])

    def test_case_and_spaces_do_not_make_two_people(self):
        self._user("kim", email="Shared@Example.com ", first_name=" Kim ")
        self._user("kim2", email="shared@example.com")
        counts = self._counts()
        self.assertEqual(
            (2, "1 share a name and address"), counts["Offered, shared identity"]
        )

    def test_never_logged_in_is_offered_not_linked(self):
        self._user("kim", last_login=None)
        counts = self._counts()
        self.assertEqual((1, ""), counts["Offered, never logged in"])
        self.assertEqual((0, ""), counts["Would link silently"])

    def test_elevated_accounts_are_asked_about(self):
        user = self._user("kim")
        self.org.add_roles(user, ROLE_ORG_MANAGER)
        counts = self._counts()
        self.assertEqual((1, "org roles or staff"), counts["Needs the other login"])
        self.assertEqual((0, ""), counts["Would link silently"])

    def test_accounts_already_holding_the_provider_are_out(self):
        user = self._user("kim")
        user.social_auth.create(provider=SCOUTID_PROVIDER, uid="a-sub", extra_data={})
        counts = self._counts()
        self.assertEqual((0, ""), counts["Active accounts without scoutid"])

    def test_ambiguous_listing_names_the_address(self):
        """
        The point of the listing is chasing the collisions down.
        """
        self._user("kim", email="shared@example.com")
        self._user("kim2", email="shared@example.com")
        self.assertIn("shared@example.com", self._run(show_ambiguous=True))

    def test_a_shared_address_under_two_names_is_counted(self):
        """
        info@someorg.org, or a couple sharing one mailbox. Each of them will be
        offered the others.
        """
        self._user("kim", email="shared@example.com")
        self._user("sam", email="shared@example.com", first_name="Sam")
        counts = self._counts()
        self.assertEqual(
            (1, "each offers the others too"),
            counts["Addresses under more than one name"],
        )
        # Different names, so each is still the only exact match for their own.
        self.assertEqual((2, ""), counts["Would link silently"])

    def test_the_buckets_account_for_everyone_reachable(self):
        self._user("linked")
        self._user("stale", email="stale@example.com", last_login=None)
        self._user("nameless", email="nameless@example.com", last_name="")
        self._user("shared1", email="two@example.com")
        self._user("shared2", email="two@example.com")
        boss = self._user("boss", email="boss@example.com")
        self.org.add_roles(boss, ROLE_ORG_MANAGER)
        counts = self._counts()
        buckets = (
            counts["Would link silently"][0]
            + counts["Offered, never logged in"][0]
            + counts["Offered, shared identity"][0]
            + counts["Offered, no full name"][0]
            + counts["Needs the other login"][0]
        )
        self.assertEqual(counts["reachable at an address"][0], buckets)
