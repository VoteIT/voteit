import os
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.organisation.models import Organisation


class MixedInvitesIntegrationTests(TestCase):
    """
    We'll call the management command with fixtures to test
    """

    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        import voteit.invites.tests

        cls.meeting = Meeting.objects.get(pk=1)
        cls.org = Organisation.objects.get(pk=1)
        cls.vader = cls.org.users.create(username="vader")
        cls.fixtures_dir = os.path.join(
            os.path.dirname(os.path.abspath(voteit.invites.tests.__file__)), "fixtures"
        )

    def fixture_file(self, filename):
        return os.path.join(self.fixtures_dir, filename)

    def call_command(self, *args, **kwargs):
        out = StringIO()
        kwargs.setdefault("q", True)
        call_command(
            "add_mixed_invites",
            *args,
            stdout=out,
            **kwargs,
        )
        return out.getvalue()

    def test_role_update(self):
        self.assertFalse(self.meeting.get_roles(self.vader))
        self.call_command(m=self.meeting.pk, u=1, f=self.fixture_file("grouprole.csv"))
        inv = self.meeting.invites.find_invites(email="vader@betahaus.net").first()
        self.assertTrue(inv)
        inv.accept(self.vader)
        inv.save()
        self.assertEqual({ROLE_PARTICIPANT}, self.meeting.get_roles(self.vader))
        self.call_command(
            m=self.meeting.pk, u=1, D=True, f=self.fixture_file("grouprole.csv")
        )
        self.assertEqual(
            {ROLE_PARTICIPANT, ROLE_DISCUSSER}, self.meeting.get_roles(self.vader)
        )
