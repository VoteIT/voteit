from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.poll.models import Poll
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.app.er_policies.manual import Manual

User = get_user_model()


class ManualERTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(er_policy_name=Manual.name)
        cls.user1 = User.objects.create(username="one")
        cls.user2 = User.objects.create(username="two")
        cls.meeting.add_roles(cls.user1, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.user2, ROLE_POTENTIAL_VOTER)
        cls.poll = Poll.objects.create(meeting=cls.meeting, method_name="simple")

    def setUp(self):
        self.meeting.refresh_from_db()
        self.poll.refresh_from_db()

    @property
    def ElectoralRegister(self):
        from voteit.poll.models import ElectoralRegister

        return ElectoralRegister

    def test_new_er_needed_when_weight_changes(self):
        self.meeting.er_policy.create_er(self.meeting, weight_dict={})
        self.assertTrue(
            self.meeting.er_policy.new_er_needed(weight_dict={self.user1.pk: 2})
        )

    def test_get_voters(self):
        weight_dict = {
            -1: 0,
            self.user1.pk: 5,
            self.user2.pk: 10,
        }
        voter_dict = self.meeting.er_policy.get_voters(weight_dict=weight_dict)
        self.assertEqual({self.user1.pk: 5, self.user2.pk: 10}, voter_dict)
