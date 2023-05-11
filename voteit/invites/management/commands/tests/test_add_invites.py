import os
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from voteit.invites.testing import fixture_file
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.organisation.models import Organisation


class InviteAnnotationsIntegrationTests(TestCase):
    """
    We'll call the management command with fixtures to test
    """

    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.org = Organisation.objects.get(pk=1)

    def call_command(self, *args, **kwargs):
        out = StringIO()
        call_command(
            "add_invites",
            *args,
            stdout=out,
            **kwargs,
        )
        return out.getvalue()

    def test_add(self):
        self.call_command(m=self.meeting.pk, u=1, f=fixture_file("emails.txt"), D=True)
        inv = self.meeting.invites.find_invites(email="a@betahaus.net").first()
        self.assertTrue(inv)
        self.assertEqual([ROLE_DISCUSSER, ROLE_PARTICIPANT], inv.roles)

    def test_roles_updated_for_existing(self):
        invite = self.meeting.invites.create(
            user_data={"email": "a@betahaus.net"}, roles=[ROLE_PARTICIPANT]
        )
        user = self.org.users.create(username="invitee")
        invite.accept(user)
        invite.save()
        self.assertEqual({ROLE_PARTICIPANT}, self.meeting.get_roles(user))
        self.call_command(
            m=self.meeting.pk,
            u=1,
            f=fixture_file("emails.txt"),
            P=True,
            V=True,
        )
        # Discusser removed, other roles set
        self.assertEqual(
            {ROLE_PARTICIPANT, ROLE_POTENTIAL_VOTER, ROLE_PROPOSER},
            self.meeting.get_roles(user),
        )

    def test_state_updated_for_existing(self):
        invite = self.meeting.invites.create(
            user_data={"email": "a@betahaus.net"}, roles=[ROLE_PARTICIPANT]
        )
        user = self.org.users.create(username="invitee")
        invite.reject(user)
        invite.save()
        self.call_command(
            m=self.meeting.pk,
            u=1,
            f=fixture_file("emails.txt"),
        )
        invite.refresh_from_db()
        self.assertEqual("open", invite.state)
