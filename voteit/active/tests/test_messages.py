from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from django.utils.timezone import now
from envelope.messages.errors import BadRequestError
from envelope.messages.errors import UnauthorizedError

from voteit.active.components import ActiveUsersComponent
from voteit.active.messages import PurgeInactiveUsers
from voteit.active.messages import SetActive
from voteit.core.workflows import EnabledWf
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.workflows import MeetingWf

User = get_user_model()

_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SetActiveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.participant = User.objects.create(username="participant")
        cls.moderator = User.objects.create(username="moderator")
        cls.active_user = User.objects.create(username="active")
        cls.meeting: Meeting = Meeting.objects.create()
        cls.component = cls.meeting.components.create(
            component_name=ActiveUsersComponent.name, state=EnabledWf.ON
        )
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.active_user, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.active = cls.meeting.active_users.create(user=cls.active_user)

    def _mk_msg(self, actor, *, active, user=None):
        return SetActive(
            mm={"user_pk": actor.pk, "consumer_name": "abc"},
            channel_type=MeetingChannel.name,
            meeting=self.meeting.pk,
            user=user,
            active=active,
        )

    def test_moderator_can_set_other_users(self):
        msg = self._mk_msg(self.moderator, user=self.participant, active=True)
        msg.run_job()
        self.assertTrue(
            self.meeting.active_users.filter(user=self.participant).exists()
        )

    def test_participants_cant_set_other_users(self):
        msg = self._mk_msg(self.participant, user=self.moderator, active=True)
        with self.assertRaises(UnauthorizedError) as cm:
            msg.run_job()
        self.assertEqual("active.change_activeuser", cm.exception.data.permission)

    def test_participant(self):
        msg = self._mk_msg(self.participant, active=True)
        msg.run_job()
        self.assertTrue(
            self.meeting.active_users.filter(user=self.participant).exists()
        )

    def test_closed_meeting(self):
        self.meeting.state = MeetingWf.CLOSED
        self.meeting.save()
        msg = self._mk_msg(self.moderator, active=True)
        with self.assertRaises(UnauthorizedError) as cm:
            msg.run_job()
        self.assertEqual("active.change_activeuser", cm.exception.data.permission)

    def test_user_outside_of_meeting_moderator(self):
        self.meeting.remove_roles(self.participant, ROLE_PARTICIPANT)
        msg = self._mk_msg(self.moderator, active=True, user=self.participant)
        with self.assertRaises(BadRequestError) as cm:
            msg.run_job()
        self.assertEqual("User not part of meeting", cm.exception.data.msg)

    def test_component_disabled(self):
        self.component.disable()
        self.component.save()
        msg = self._mk_msg(self.moderator, active=True)
        with self.assertRaises(UnauthorizedError) as cm:
            msg.run_job()
        self.assertEqual("active.change_activeuser", cm.exception.data.permission)

    def test_remove_active(self):
        msg = self._mk_msg(self.moderator, active=False, user=self.active_user)
        msg.run_job()
        self.assertFalse(
            self.meeting.active_users.filter(user=self.active_user).exists()
        )


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class PurgeInactiveUsersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.participant = User.objects.create(username="participant")
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting: Meeting = Meeting.objects.create()
        cls.component = cls.meeting.components.create(
            component_name=ActiveUsersComponent.name, state=EnabledWf.ON
        )
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.active_participant = cls.meeting.active_users.create(user=cls.participant)
        cls.active_moderator = cls.meeting.active_users.create(user=cls.moderator)
        cls.mod_con = cls.moderator.connections.create(last_action=now())
        cls.participant_con = cls.participant.connections.create(
            last_action=now() - timedelta(days=1)
        )

    def _mk_msg(self, actor, hours: int = 1):
        return PurgeInactiveUsers(
            mm={"user_pk": actor.pk, "consumer_name": "abc"},
            meeting=self.meeting.pk,
            hours=hours,
        )

    @patch.object(MeetingChannel, "sync_publish")
    def test_purge(self, mock_publish):
        msg = self._mk_msg(self.moderator)
        with self.captureOnCommitCallbacks(execute=True):
            msg.run_job()
        self.assertEqual(1, self.meeting.active_users.count())
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertEqual(
            {"active": False, "meeting": self.meeting.pk, "user": self.participant.pk},
            msg.data.dict(),
        )

    def test_participant_perm(self):
        msg = self._mk_msg(self.participant)
        with self.assertRaises(UnauthorizedError) as cm:
            msg.run_job()
        self.assertEqual("meeting.change_meeting", cm.exception.data.permission)

    def test_purge_higher_number(self):
        msg = self._mk_msg(self.moderator, hours=48)
        msg.run_job()
        self.assertEqual(2, self.meeting.active_users.count())
