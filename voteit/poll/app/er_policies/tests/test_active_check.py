from django.contrib.auth import get_user_model
from django.test import TestCase
from django_fsm import TransitionNotAllowed

from voteit.active.components import ActiveUsersComponent
from voteit.core.workflows import EnabledWf
from voteit.poll.app.er_policies.active_check import ActiveCheckPolicy
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.app.er_policies.auto_before_poll import AutoBeforePoll

User = get_user_model()


class ActiveCheckPolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            er_policy_name=ActiveCheckPolicy.name
        )
        cls.user1 = User.objects.create(username="one")
        cls.user2 = User.objects.create(username="two")
        cls.meeting.add_roles(cls.user1, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.user2, ROLE_POTENTIAL_VOTER)
        cls.meeting.components.create(
            component_name=ActiveUsersComponent.name, state=EnabledWf.ON
        )
        cls.active1 = cls.meeting.active_users.create(user=cls.user1)
        cls.active2 = cls.meeting.active_users.create(user=cls.user2)
        cls.poll = Poll.objects.create(meeting=cls.meeting, method_name="simple")

    # def setUp(self):
    #     self.meeting.refresh_from_db()
    #     self.poll.refresh_from_db()

    def test_new_er_on_upcoming(self):
        self.poll.upcoming()
        self.assertIsInstance(self.poll.electoral_register, ElectoralRegister)
        # Why self.assertQuerysetEqual() create object strings of some kind?
        self.assertEqual(
            {self.user1, self.user2}, set(self.poll.electoral_register.voters.all())
        )

    def test_new_er_one_user_inactive(self):
        first_er = self.meeting.er_policy.create_er()
        self.active2.delete()
        second_er = self.meeting.er_policy.create_er()
        self.assertNotEqual(first_er, second_er)
        self.assertEqual({self.user1.pk: 1}, second_er.weight_dict)

    def test_same_er_on_start_if_no_new_users(self):
        first_er = self.meeting.er_policy.create_er()
        self.poll.upcoming()
        self.poll.unpublish()
        self.poll.upcoming()
        self.assertEqual(first_er, self.poll.electoral_register)
        self.assertEqual(first_er, self.meeting.get_latest_er())

    def test_get_voters_when_switching_to_groups(self):
        self.assertEqual(
            {self.user1.pk: 1, self.user2.pk: 1}, self.meeting.er_policy.get_voters()
        )
        self.meeting.group_votes_active = True
        self.meeting.save()
        self.assertEqual({}, self.meeting.er_policy.get_voters())
        group = self.meeting.groups.create(groupid="group", votes=4)
        group.members.add(self.user1, self.user2)
        self.assertEqual(
            {self.user1.pk: 2, self.user2.pk: 2}, self.meeting.er_policy.get_voters()
        )
        self.active1.delete()
        self.assertEqual({self.user2.pk: 4}, self.meeting.er_policy.get_voters())

    def test_poll_will_have_voters(self):
        self.assertTrue(self.meeting.er_policy.poll_will_have_voters())
        self.active1.delete()
        self.active2.delete()
        self.assertFalse(self.meeting.er_policy.poll_will_have_voters())
