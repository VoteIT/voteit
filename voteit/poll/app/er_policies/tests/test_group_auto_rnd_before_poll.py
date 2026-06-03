from random import Random

from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.active.components import ActiveUsersComponent
from voteit.meeting.models import MeetingGroup
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.app.er_policies.group_auto_rnd_before_poll import (
    GroupAutoRandomBeforePoll,
)

User = get_user_model()


class GroupAutoRandomBeforePollTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            er_policy_name=GroupAutoRandomBeforePoll.name, group_votes_active=True
        )
        cls.ai = cls.meeting.agenda_items.create()
        cls.user1 = User.objects.create(username="one")
        cls.user2 = User.objects.create(username="two")
        cls.meeting.add_roles(cls.user1, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.user2, ROLE_POTENTIAL_VOTER)
        cls.group_l: MeetingGroup = cls.meeting.groups.create(title="Large", votes=10)
        cls.group_s: MeetingGroup = cls.meeting.groups.create(title="Small", votes=1)
        cls.group_l.members.add(cls.user1, cls.user2)
        cls.group_s.members.add(cls.user1)
        cls.poll = Poll.objects.create(meeting=cls.meeting, method_name="simple")

    def setUp(self):
        self.meeting.refresh_from_db()
        self.poll.refresh_from_db()

    def test_new_er_on_upcoming(self):
        self.poll.upcoming()
        self.assertIsInstance(self.poll.electoral_register, ElectoralRegister)
        self.assertEqual(
            {self.user1.pk: 6, self.user2.pk: 5},
            self.poll.electoral_register.weight_dict,
        )

    def test_rnd_with_same_seed_keeps_er(self):
        # Unequal votes
        self.group_l.votes = 3
        self.group_l.save()
        # Meeting pk is used for rnd seed
        rnd = Random(self.meeting.pk)
        user_pks = [self.user1.pk, self.user2.pk]
        rnd.shuffle(user_pks)
        first_er = self.meeting.er_policy.create_er()
        # Where did the extra vote from group_l go?
        if user_pks == [self.user1.pk, self.user2.pk]:
            self.assertEqual({self.user1.pk: 3, self.user2.pk: 1}, first_er.weight_dict)
        else:
            self.assertEqual({self.user1.pk: 2, self.user2.pk: 2}, first_er.weight_dict)
        self.assertEqual(first_er, self.meeting.er_policy.create_er())

    def test_potential_voter_needed(self):
        self.meeting.remove_roles(self.user1, ROLE_POTENTIAL_VOTER)
        first_er = self.meeting.er_policy.create_er()
        self.assertEqual({self.user2.pk: 10}, first_er.weight_dict)

    def test_active_users_respected(self):
        self.meeting.components.create(
            component_name=ActiveUsersComponent.name, enabled=True
        )
        self.meeting.active_users.create(user=self.user1)
        self.poll.upcoming()
        self.assertEqual(
            {self.user1.pk},
            {int(k) for k in self.poll.electoral_register.voter_data.keys()},
        )

    def test_delegate_to(self):
        self.meeting.components.create(
            component_name=ActiveUsersComponent.name, enabled=True
        )
        self.meeting.active_users.create(user=self.user2)
        self.group_s.delegate_to = self.group_l
        self.group_s.save()
        er = self.meeting.er_policy.create_er()
        self.assertEqual({self.user2.pk: 11}, er.weight_dict)
