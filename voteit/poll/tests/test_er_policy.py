from __future__ import annotations

from random import seed

from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.app.er_policies.auto_before_poll import AutoBeforePoll


User = get_user_model()


class ElectoralRegisterPolicyTests(TestCase):
    ...


class GroupVoteElectoralRegisterPolicyTests(TestCase):
    """
    We'll use the auto before poll method to test the abstract methods
    """

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create(
            er_policy_name=AutoBeforePoll.name, group_votes_active=True
        )
        cls.one = User.objects.create(username="one")
        cls.two = User.objects.create(username="two")
        cls.three = User.objects.create(username="three")
        cls.meeting.add_roles(cls.one, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.two, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.three, ROLE_POTENTIAL_VOTER)
        cls.group_one = cls.meeting.groups.create(groupid="one")
        cls.group_two = cls.meeting.groups.create(groupid="two")
        cls.group_one.members.add(cls.one, cls.two, cls.three)
        cls.group_two.members.add(cls.one, cls.two, cls.three)

    def test_calc_group_votes_equal_one_group_with_votes(self):
        self.group_one.votes = 6
        self.group_one.save()
        self.assertEqual(
            {self.one.pk: 2, self.two.pk: 2, self.three.pk: 2},
            self.meeting.er_policy.calc_group_votes_equal(),
        )

    def test_calc_group_votes_equal_potential_voters_respected(self):
        self.group_one.votes = 6
        self.group_one.save()
        self.meeting.remove_roles(self.one, ROLE_POTENTIAL_VOTER)
        self.assertEqual(
            {self.two.pk: 3, self.three.pk: 3},
            self.meeting.er_policy.calc_group_votes_equal(),
        )

    def test_calc_group_votes_equal_unequal_votes(self):
        seed(1337)
        self.group_one.votes = 3
        self.group_one.save()
        self.group_two.votes = 2
        self.group_two.save()
        self.assertEqual(
            {self.one.pk: 2, self.two.pk: 2, self.three.pk: 1},
            self.meeting.er_policy.calc_group_votes_equal(),
        )

    def test_calc_group_votes_equal_filter(self):
        self.group_one.votes = 2
        self.group_one.save()
        users_qs = User.objects.filter(pk=self.one.pk)
        self.assertEqual(
            {self.one.pk: 2},
            self.meeting.er_policy.calc_group_votes_equal(only_users_qs=users_qs),
        )

    def test_calc_group_votes_equal_singular_groups(self):
        self.group_one.votes = 3
        self.group_one.save()
        self.group_one.members.set([self.one])
        self.group_two.votes = 2
        self.group_two.save()
        self.group_two.members.set([self.two])
        self.assertEqual(
            {self.one.pk: 3, self.two.pk: 2},
            self.meeting.er_policy.calc_group_votes_equal(),
        )

    def test_calc_group_votes_equal_no_intersections(self):
        self.group_one.votes = 3
        self.group_one.save()
        self.group_one.members.set([self.one])
        self.group_two.votes = 2
        self.group_two.save()
        self.group_two.members.set([self.two])
        users_qs = User.objects.filter(pk=self.three.pk)
        self.assertEqual(
            {},
            self.meeting.er_policy.calc_group_votes_equal(only_users_qs=users_qs),
        )

    def test_new_er_needed_when_groups_change(self):
        self.group_one.votes = 3
        self.group_one.save()
        self.group_two.votes = 2
        self.group_two.save()
        er_one = self.meeting.er_policy.create_er()
        self.assertIsNotNone(er_one)
        self.group_two.votes = 4
        self.group_two.save()
        er_two = self.meeting.er_policy.create_er()
        self.assertNotEqual(er_one, er_two)
