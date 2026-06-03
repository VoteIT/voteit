from django.contrib.auth import get_user_model
from django.test import TestCase
from django_fsm import TransitionNotAllowed

from voteit.active.components import ActiveUsersComponent
from voteit.poll.models import Poll
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.app.er_policies.manual_trigger import ManualTrigger

User = get_user_model()


class ManualTriggerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(er_policy_name=ManualTrigger.name)
        cls.ai = cls.meeting.agenda_items.create()
        cls.user1 = User.objects.create(username="one")
        cls.user2 = User.objects.create(username="two")
        cls.meeting.add_roles(cls.user1, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.user2, ROLE_POTENTIAL_VOTER)
        cls.poll = Poll.objects.create(meeting=cls.meeting, method_name="simple")

    def setUp(self):
        self.meeting.refresh_from_db()
        self.poll.refresh_from_db()

    def test_no_new_er_on_poll_change(self):
        self.poll.upcoming()
        self.assertIsNone(self.poll.electoral_register)
        with self.assertRaises(TransitionNotAllowed):
            self.poll.ongoing()

    def test_active_users_respected(self):
        self.meeting.components.create(
            component_name=ActiveUsersComponent.name, enabled=True
        )
        self.meeting.active_users.create(user=self.user1)
        self.meeting.er_policy.create_er()
        self.assertEqual(
            {self.user1.pk},
            {int(k) for k in self.meeting.latest_er.voter_data.keys()},
        )
