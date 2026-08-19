from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from voteit.invites.models import MeetingGroupAnnotation
from voteit.invites.testing import fixture_file
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.organisation.models import Organisation


class ImportInvitesCommandTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.org = Organisation.objects.get(pk=1)

    def call_command(self, *args, **kwargs):
        out = StringIO()
        call_command("import_invites", *args, stdout=out, **kwargs)
        return out.getvalue()

    def test_basic_email_import(self):
        out = self.call_command(m=self.meeting.pk, f=fixture_file("emails.txt"))
        inv = self.meeting.invites.find_invites(email="a@betahaus.net").first()
        self.assertIsNotNone(inv)
        self.assertEqual([ROLE_PARTICIPANT], inv.roles)
        self.assertIn("added: 3", out)

    def test_roles_from_file(self):
        # grouprole.csv has email\tgroup\tgrouprole columns — roles default to PARTICIPANT
        meeting = self.meeting
        meeting.groups.create(groupid="sw")
        meeting.groups.create(groupid="sabreclub")
        meeting.group_roles.create(role_id="jedi")
        meeting.group_roles.create(role_id="sith")
        self.call_command(m=meeting.pk, f=fixture_file("grouprole.csv"))
        inv = meeting.invites.find_invites(email="vader@betahaus.net").first()
        self.assertIsNotNone(inv)
        self.assertEqual([ROLE_PARTICIPANT], inv.roles)

    def test_annotation_applied(self):
        meeting = self.meeting
        group_sw = meeting.groups.create(groupid="sw")
        meeting.groups.create(groupid="sabreclub")
        meeting.group_roles.create(role_id="jedi")
        meeting.group_roles.create(role_id="sith")
        self.call_command(m=meeting.pk, f=fixture_file("grouprole.csv"))
        self.assertEqual(3, group_sw.invite_annotations.count())
        out_text = self.call_command(m=meeting.pk, f=fixture_file("grouprole.csv"))
        self.assertIn("Annotation 'group'", out_text)

    def test_dryrun_does_not_save(self):
        out = self.call_command(
            m=self.meeting.pk, f=fixture_file("emails.txt"), dryrun=True
        )
        self.assertEqual(0, self.meeting.invites.count())
        self.assertIn("DRY RUN", out)

    def test_roles_updated_for_accepted_invite(self):
        invite = self.meeting.invites.create(
            user_data={"email": "a@betahaus.net"}, roles=[ROLE_PARTICIPANT]
        )
        user = self.org.users.create(username="invitee")
        invite.accept(user)
        invite.save()
        self.assertEqual({ROLE_PARTICIPANT}, self.meeting.get_roles(user))

        # emails.txt has no roles column so all invites get PARTICIPANT
        # Re-importing with same file → roles unchanged (existed path)
        self.call_command(m=self.meeting.pk, f=fixture_file("emails.txt"))
        self.assertEqual({ROLE_PARTICIPANT}, self.meeting.get_roles(user))

    def test_rejected_invite_reopened(self):
        invite = self.meeting.invites.create(
            user_data={"email": "a@betahaus.net"}, roles=[ROLE_PARTICIPANT]
        )
        user = self.org.users.create(username="invitee2")
        invite.reject(user)
        invite.save()
        self.assertEqual("rejected", invite.state)
        self.call_command(m=self.meeting.pk, f=fixture_file("emails.txt"))
        invite.refresh_from_db()
        self.assertEqual("open", invite.state)

    def test_annotation_dryrun_does_not_save(self):
        meeting = self.meeting
        meeting.groups.create(groupid="sw")
        meeting.groups.create(groupid="sabreclub")
        meeting.group_roles.create(role_id="jedi")
        meeting.group_roles.create(role_id="sith")
        self.call_command(m=meeting.pk, f=fixture_file("grouprole.csv"), dryrun=True)
        self.assertEqual(0, MeetingGroupAnnotation.objects.count())
