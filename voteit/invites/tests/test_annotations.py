import os
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from voteit.meeting.models import Meeting
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
        cls.group_sw = cls.meeting.groups.create(groupid="sw")
        cls.group_sabreclub = cls.meeting.groups.create(groupid="sabreclub")
        cls.role_jedi = cls.meeting.group_roles.create(role_id="jedi")
        cls.role_sith = cls.meeting.group_roles.create(role_id="sith")
        cls.vader = cls.org.users.create(username="vader")

    def fixture_file(self, filename):
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "fixtures",
            filename,
        )

    def call_command(self, *args, **kwargs):
        out = StringIO()
        call_command(
            "add_annotated_invites",
            *args,
            stdout=out,
            **kwargs,
        )
        return out.getvalue()

    def test_group(self):
        self.call_command(m=self.meeting.pk, u=1, f=self.fixture_file("grouprole.csv"))
        self.assertEqual(3, self.group_sw.invite_annotations.count())
        inv = self.meeting.invites.find_invites(email="vader@betahaus.net").first()
        self.assertTrue(inv)
        inv.accept(self.vader)
        members = self.group_sw.memberships.all()
        self.assertEqual(1, members.count())
        membership = members.first()
        self.assertEqual(self.role_sith, membership.role)
        self.assertEqual(self.vader, inv.used_by)
        self.assertEqual(self.vader, membership.user)

    def test_updates_for_used_invite(self):
        self.call_command(m=self.meeting.pk, u=1, f=self.fixture_file("grouprole.csv"))
        self.assertEqual(3, self.group_sw.invite_annotations.count())
        inv = self.meeting.invites.find_invites(email="vader@betahaus.net").first()
        self.assertTrue(inv)
        inv.accept(self.vader)
        inv.save()
        members = self.group_sw.memberships.all()
        self.assertEqual(1, members.count())
        members.delete()
        self.assertEqual(0, members.count())
        self.call_command(m=self.meeting.pk, u=1, f=self.fixture_file("grouprole.csv"))
        members = self.group_sw.memberships.all()
        self.assertEqual(1, members.count())

    def test_blank_roles_afterwards(self):
        self.call_command(m=self.meeting.pk, u=1, f=self.fixture_file("grouprole.csv"))
        self.assertEqual(
            [self.role_sith.pk, self.role_jedi.pk, None],
            [
                x["group_role_id"]
                for x in self.group_sw.invite_annotations.all().values()
            ],
        )

        self.call_command(
            m=self.meeting.pk, u=1, f=self.fixture_file("grouprole_blank.csv")
        )
        self.assertEqual(
            [None, None, None],
            [
                x["group_role_id"]
                for x in self.group_sw.invite_annotations.all().values()
            ],
        )

    def test_updates_blanks_out_role(self):
        self.call_command(m=self.meeting.pk, u=1, f=self.fixture_file("grouprole.csv"))
        inv = self.meeting.invites.find_invites(email="vader@betahaus.net").first()
        inv.accept(self.vader)
        inv.save()
        self.assertEqual(
            [self.role_sith.pk],
            [x["role_id"] for x in self.group_sw.memberships.all().values()],
        )
        self.call_command(
            m=self.meeting.pk, u=1, f=self.fixture_file("grouprole_blank.csv")
        )
        self.assertEqual(
            [None],
            [x["role_id"] for x in self.group_sw.memberships.all().values()],
        )
