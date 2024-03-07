from json import loads
from unittest import mock
from unittest.mock import patch

from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from pydantic import ValidationError
from pythonjsonlogger.jsonlogger import JsonFormatter
from envelope.consumers.websocket import WebsocketConsumer
from envelope.messages.errors import UnauthorizedError
from envelope.messages.errors import ValidationErrorMsg
from envelope.testing import testing_channel_layers_setting

from voteit.core.schemas import RoleOutput
from voteit.core.testing import FakeCommit
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT

User = get_user_model()
json_formatter = JsonFormatter()


def _record_to_dict(record):
    # Also to test jsonlogger
    output = json_formatter.format(record)
    return loads(output)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class AvalableMeetingRolesTests(TestCase):
    def _mk_one(self, **kw):
        from voteit.core.messages.roles import AvailableRoles

        return AvailableRoles(mm={"consumer_name": "abc"}, **kw)

    async def test_get_meeting_roles(self):
        from voteit.core.messages.roles import AvailableRolesResponse

        consumer = WebsocketConsumer()
        consumer.channel_name = "abc"
        consumer.base_send = mock.AsyncMock()
        msg = self._mk_one(model="meeting")
        response = await msg.run(consumer=consumer)
        self.assertIsInstance(response, AvailableRolesResponse)
        self.assertIsInstance(response.data.roles[0], RoleOutput)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class MeetingRolesTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create(username="abel")
        self.user_b = User.objects.create(username="bret")
        self.user_c = User.objects.create(username="cain")
        self.meeting = Meeting.objects.create()

    def test_get_meeting_roles_unauthorized(self):
        self.meeting.add_roles(self.user_a, ROLE_PARTICIPANT, ROLE_MODERATOR)
        from voteit.core.messages.roles import GetRoles

        msg = GetRoles(pk=self.meeting.pk, model="meeting")
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_get_meeting_roles(self):
        from voteit.core.messages.roles import GetRoles
        from voteit.core.messages.roles import AssignedRolesResponse

        self.meeting.add_roles(self.user_a, ROLE_PARTICIPANT, ROLE_MODERATOR)
        msg = GetRoles(
            mm={"user_pk": self.user_a.pk, "consumer_name": "abc"},
            pk=self.meeting.pk,
            model="meeting",
        )
        channel_layer = get_channel_layer()
        with patch.object(channel_layer, "send") as mock_method:
            response = msg.run_job()
            self.assertTrue(mock_method.called)
            self.assertIsInstance(response, AssignedRolesResponse)
            data = response.data
            self.assertEqual(1, len(data.items))
            self.assertIn(self.user_a.pk, [x[0] for x in data.items])
            self.assertEqual({ROLE_PARTICIPANT, ROLE_MODERATOR}, set(data.items[0][1]))


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class AddRolesTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")

    def _mk_msg(self, actor, users, roles):
        from voteit.core.messages.roles import AddRoles

        return AddRoles(
            mm={"user_pk": actor.pk, "consumer_name": "abc"},
            users=users,
            roles=roles,
            pk=self.meeting.pk,
            model="meeting",
        )

    def test_change_gets_logged(self):
        msg = self._mk_msg(self.moderator, [self.participant.pk], [str(ROLE_DISCUSSER)])
        with self.assertLogs("voteit.event.roles") as logs:
            with FakeCommit():
                msg.run_job()
                self.assertEqual(0, len(logs.records))
            self.assertEqual(1, len(logs.records))
        data = _record_to_dict(logs.records[0])
        data.pop("taskName", None)  # Not important here
        self.assertEqual(
            {
                "message": "Added",
                "context_name": "meeting",
                "context": 1,
                "org": 1,
                "meeting": 1,
                "actor": 1,
                "for_user": 2,
                "roles": [ROLE_DISCUSSER],
            },
            data,
        )

    def test_permission_checked(self):
        msg = self._mk_msg(
            self.participant, [self.participant.pk], [str(ROLE_DISCUSSER)]
        )
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_bad_user_pks(self):
        msg = self._mk_msg(self.moderator, [-1], [ROLE_DISCUSSER])
        self.assertRaises(ValidationErrorMsg, msg.run_job)

    def test_bad_role(self):
        with self.assertRaises(ValidationError):
            msg = self._mk_msg(self.moderator, [self.participant.pk], ["jeff"])


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class RemoveRolesTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")

    def _mk_msg(self, actor, users, roles):
        from voteit.core.messages.roles import RemoveRoles

        return RemoveRoles(
            mm={"user_pk": actor.pk, "consumer_name": "abc"},
            users=users,
            roles=roles,
            pk=self.meeting.pk,
            model="meeting",
        )

    def test_change_gets_logged(self):
        msg = self._mk_msg(
            self.moderator, [self.participant.pk], [str(ROLE_PARTICIPANT)]
        )
        with self.assertLogs("voteit.event.roles") as logs:
            with FakeCommit():
                msg.run_job()
                self.assertEqual(0, len(logs.records))
            self.assertEqual(1, len(logs.records))
        data = _record_to_dict(logs.records[0])
        data.pop("taskName", None)  # Not important here
        self.assertEqual(
            {
                "message": "Removed",
                "context_name": "meeting",
                "context": 1,
                "meeting": 1,
                "org": 1,
                "actor": 1,
                "for_user": 2,
                "roles": [str(ROLE_PARTICIPANT)],
            },
            data,
        )

    def test_permission_checked(self):
        msg = self._mk_msg(
            self.participant, [self.participant.pk], [str(ROLE_DISCUSSER)]
        )
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_bad_user_pks(self):
        msg = self._mk_msg(self.moderator, [-1], [str(ROLE_DISCUSSER)])
        self.assertRaises(ValidationErrorMsg, msg.run_job)

    def test_bad_role(self):
        with self.assertRaises(ValidationError):
            msg = self._mk_msg(self.moderator, [self.participant.pk], ["jeff"])
