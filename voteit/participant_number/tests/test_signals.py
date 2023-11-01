from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from envelope.messages.channels import Subscribe
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SignalsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.participant_number.models import PNSystem

        cls.meeting: Meeting = Meeting.objects.create()
        cls.user_a = User.objects.create(username="a")
        cls.user_b = User.objects.create(username="b")
        cls.user_c = User.objects.create(username="c")
        cls.meeting.add_roles(cls.user_a, ROLE_PARTICIPANT, ROLE_MODERATOR)
        cls.meeting.add_roles(cls.user_b, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.user_c, ROLE_PARTICIPANT)
        cls.pn_sys: PNSystem = PNSystem.objects.create(meeting=cls.meeting)
        cls.one = cls.pn_sys.numbers.create(user=cls.user_a)
        cls.two = cls.pn_sys.numbers.create(user=cls.user_b)

    def setUp(self):
        self.one.refresh_from_db()

    def test_app_state_sent(self):
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.user_a.pk},
            pk=self.meeting.pk,
            channel_type=MeetingChannel.name,
        )
        msg = command.run_job()
        pks = {x.p["pk"] for x in msg.data.app_state if x.t == "pn.added"}
        self.assertEqual({self.one.pk, self.two.pk}, pks)

    @patch.object(MeetingChannel, "sync_publish")
    def test_added_pn(self, mock_publish):
        from voteit.participant_number.messages import PNAdded

        self.assertFalse(mock_publish.called)
        pn = self.pn_sys.numbers.create(user=self.user_c)
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PNAdded)
        self.assertEqual(pn.pk, msg.data.pk)
        self.assertEqual(pn.number, msg.data.number)
        self.assertEqual(3, pn.number)

    @patch.object(MeetingChannel, "sync_publish")
    def test_pn_changed(self, mock_publish):
        from voteit.participant_number.messages import PNChanged

        self.assertFalse(mock_publish.called)
        self.one.number = 10
        self.one.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PNChanged)
        self.assertEqual(self.one.number, msg.data.number)

    @patch.object(MeetingChannel, "sync_publish")
    def test_pn_deleted(self, mock_publish):
        from voteit.participant_number.messages import PNDeleted

        self.assertFalse(mock_publish.called)
        pn_pk = self.one.pk
        self.one.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PNDeleted)
        self.assertEqual(pn_pk, msg.data.pk)
