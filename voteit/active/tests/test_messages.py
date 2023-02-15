from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from envelope.messages.errors import BadRequestError
from envelope.messages.errors import UnauthorizedError

from voteit.active.components import ActiveUsersComponent
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
