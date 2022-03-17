from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.test import override_settings
from django.utils.timezone import now
from voteit.core.testing import FakeCommit
from voteit.invites.channels import MeetingInvitesChannel
from voteit.core.workflows import SendWf

if TYPE_CHECKING:
    from voteit.invites.messages import AddInvites
    from voteit.invites.messages import SendInvites

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AddInvitesTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @property
    def _cut(self):
        from voteit.invites.messages import AddInvites

        return AddInvites

    def _mk_one(self, user_pk: int = None, **kw) -> AddInvites:
        if user_pk is None:
            user_pk = 1  # Moderator from fixture
        kw.setdefault("meeting", 1)  # from fixture
        return self._cut(mm={"consumer_name": "abc", "user_pk": user_pk}, **kw)

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_add(self, mock_publish):
        from voteit.invites.messages import MeetingInviteAdded

        data = []
        for name in ["one", "two", "three"]:
            data.append(f"{name}@betahaus.net")
        msg = self._mk_one(invite_data=data, roles=["participant"])
        with FakeCommit():
            response = msg.run_job()
        self.assertEqual(3, len(response.data.added))
        self.assertEqual(0, len(response.data.changed))
        self.assertEqual(0, response.data.skipped_count)
        # Check pushes
        self.assertTrue(mock_publish.called)
        self.assertEqual(3, len(mock_publish.mock_calls))
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingInviteAdded)
        self.assertEqual("one@betahaus.net", msg.data.invite_data)

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_add_modifies_already_existing_invites(self, mock_publish):
        from voteit.meeting.models import Meeting
        from voteit.invites.messages import MeetingInviteAdded
        from voteit.invites.messages import MeetingInviteChanged
        from voteit.invites.models import MeetingInvite
        from voteit.invites.workflows import InviteWf

        meeting: Meeting = Meeting.objects.get(pk=1)  # From fixture
        moderator = User.objects.get(username="moderator")
        diffing_data_invite: MeetingInvite = meeting.invites.create(
            invite_data="one@betahaus.net",
            roles=["voter"],
            created_by=moderator,
        )
        rejected_invite: MeetingInvite = meeting.invites.create(
            invite_data="two@betahaus.net",
            roles=["participant", "voter"],
            state=InviteWf.REJECTED,
            created_by=moderator,
        )
        mock_publish.reset_mock()
        data = []
        for name in ["one", "two", "three"]:
            data.append(f"{name}@betahaus.net")
        msg = self._mk_one(
            user_pk=moderator.pk, invite_data=data, roles=["participant"]
        )
        with FakeCommit():
            response = msg.run_job()
        self.assertEqual(1, len(response.data.added))
        self.assertEqual(1, len(response.data.changed))
        self.assertEqual(1, response.data.skipped_count)
        # Check pushes
        self.assertTrue(mock_publish.called)
        self.assertEqual(2, len(mock_publish.mock_calls))
        changed_msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(changed_msg, MeetingInviteChanged)
        self.assertEqual(["participant"], changed_msg.data.roles)
        added_msg = mock_publish.mock_calls[1].args[0]
        self.assertIsInstance(added_msg, MeetingInviteAdded)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SendInvitesTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.invites.models import MeetingInvite

        cls.moderator = User.objects.get(username="moderator")
        cls.meeting: Meeting = Meeting.objects.get(pk=1)  # From fixture
        cls.inv1: MeetingInvite = cls.meeting.invites.create(
            invite_data="one@betahaus.net",
            created_by=cls.moderator,
            roles=["participant"],
        )
        cls.inv2: MeetingInvite = cls.meeting.invites.create(
            invite_data="two@betahaus.net",
            created_by=cls.moderator,
            roles=["participant"],
        )

    def setUp(self):
        self.inv1.refresh_from_db()
        self.inv2.refresh_from_db()

    @property
    def _cut(self):
        from voteit.invites.messages import SendInvites

        return SendInvites

    def _mk_one(self, user_pk: int = None, **kw) -> SendInvites:
        if user_pk is None:
            user_pk = 1  # Moderator from fixture
        kw.setdefault("meeting", 1)  # from fixture
        kw.setdefault("body", "hello world")
        kw.setdefault("subject", "About this meeting")
        return self._cut(mm={"consumer_name": "abc", "user_pk": user_pk}, **kw)

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_send(self, mock_publish):
        from voteit.invites.messages import MeetingInviteChanged

        msg = self._mk_one()
        with FakeCommit():
            msg.run_job()
        self.assertTrue(mock_publish.called)

        messages = [
            x
            for x in mock_publish.mock_calls
            if x.args[0].name == MeetingInviteChanged.name
        ]
        self.assertEqual(4, len(messages))
        self.assertEqual(2, self.meeting.invites.filter(send_state=SendWf.SENT).count())
        self.assertEqual(2, len(mail.outbox))

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_send_invites_already_sent(self, mock_publish):
        self.meeting.invites.all().update(last_sent=now())
        msg = self._mk_one()
        msg.run_job()
        self.assertFalse(mock_publish.called)
        self.assertEqual(0, self.meeting.invites.filter(send_state=SendWf.SENT).count())

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_bad_data_in_invite(self, mock_publish):
        from voteit.invites.messages import MeetingInviteChanged

        self.inv1.invite_data = "jeff"
        self.inv1.save()
        mock_publish.reset_mock()
        msg = self._mk_one()
        with FakeCommit():
            msg.run_job()
        self.assertTrue(mock_publish.called)
        messages = [
            x
            for x in mock_publish.mock_calls
            if x.args[0].name == MeetingInviteChanged.name
        ]
        self.assertEqual(4, len(messages))
        self.assertEqual(1, self.meeting.invites.filter(send_state=SendWf.SENT).count())
        self.assertEqual(
            1, self.meeting.invites.filter(send_state=SendWf.FAILED).count()
        )
