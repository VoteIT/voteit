from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from voteit.messaging.testing import action_of
from voteit.messaging.testing import build_app_state

from voteit.messaging.state import AppState

from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.room.channels import RoomChannel
from voteit.room.messages import RoomChanged
from voteit.room.messages import RoomDeleted
from voteit.room.messages import RoomHighlighted
from voteit.room.models import Room

_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}

User = get_user_model()


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SubscriptionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.user = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.user, ROLE_PARTICIPANT)
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop1 = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.room = cls.meeting.rooms.create(agenda_item=cls.ai)
        cls.hl1 = cls.room.highlighted_proposals.create(proposal=cls.prop1)

    def test_subscribe_meeting(self):
        app_state = build_app_state(MeetingChannel.name, self.meeting.pk, self.user.pk)
        payloads = [
            x.payload.model_dump() for x in app_state if x.action == "room.changed"
        ]
        self.assertEqual(1, len(payloads))
        data = payloads[0]
        self.assertTrue(data.pop("created", None))
        self.assertEqual(
            {
                "open": False,
                "body": "",
                "handler": None,
                "meeting": self.meeting.pk,
                "pk": self.room.pk,
                "send_proposals": False,
                "send_sls": False,
                "show_time": True,
                "title": "",
                "agenda_item": self.ai.pk,
                "poll": None,
                "show_ballot": False,
            },
            data,
        )

    def test_subscribe_room(self):
        app_state = build_app_state(RoomChannel.name, self.room.pk, self.user.pk)
        self.assertEqual(
            [
                {
                    "highlighted": [self.prop1.pk],
                    "pk": self.room.pk,
                    "token": None,
                }
            ],
            [
                x.payload.model_dump()
                for x in app_state
                if x.action == action_of(RoomHighlighted)
            ],
        )

    def test_subscribe_room_queries(self):
        from voteit.room.signals import room_subscribed

        room = Room.objects.get(pk=self.room.pk)
        app_state = AppState()
        with self.assertNumQueries(1):
            room_subscribed(room, app_state)

    @patch.object(MeetingChannel, "sync_publish")
    def test_room_changed(self, mock_publish):
        with self.captureOnCommitCallbacks(execute=True):
            self.room.title = "Hello world"
            self.room.save()
        self.assertTrue(mock_publish.called)
        messages = [
            x.args[0]
            for x in mock_publish.mock_calls
            if isinstance(x.args[0], RoomChanged)
        ]
        msg = messages[0]
        self.assertEqual("Hello world", msg.payload.title)

    @patch.object(MeetingChannel, "sync_publish")
    def test_room_deleted(self, mock_publish):
        room_pk = self.room.pk
        with self.captureOnCommitCallbacks(execute=True):
            self.room.delete()
        self.assertTrue(mock_publish.called)
        messages = [
            x.args[0]
            for x in mock_publish.mock_calls
            if isinstance(x.args[0], RoomDeleted)
        ]
        msg = messages[0]
        self.assertEqual(room_pk, msg.payload.pk)
