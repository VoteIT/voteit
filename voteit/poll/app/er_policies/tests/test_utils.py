from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import models
from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.app.er_policies.group_auto_rnd_before_poll import (
    GroupAutoRandomBeforePoll,
)


User = get_user_model()


class CalcGroupVotesEqualTests(TestCase):
    """
    We'll use the auto before poll method to test the abstract methods
    """

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            er_policy_name=GroupAutoRandomBeforePoll.name, group_votes_active=True
        )
        cls.one = User.objects.create(username="one")
        cls.two = User.objects.create(username="two")
        cls.three = User.objects.create(username="three")
        cls.meeting.add_roles(cls.one, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.two, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.three, ROLE_POTENTIAL_VOTER)
        cls.group_one: MeetingGroup = cls.meeting.groups.create(groupid="one")
        cls.group_two: MeetingGroup = cls.meeting.groups.create(groupid="two")
        cls.group_one.members.add(cls.one, cls.two, cls.three)
        cls.group_two.members.add(cls.one, cls.two, cls.three)

    @property
    def _fut(self):
        from voteit.poll.app.er_policies.utils import calc_group_votes_equal

        return calc_group_votes_equal

    def test_calc_group_votes_equal_one_group_with_votes(self):
        self.group_one.votes = 6
        self.group_one.save()
        self.assertEqual(
            {self.one.pk: 2, self.two.pk: 2, self.three.pk: 2},
            self._fut(meeting=self.meeting),
        )

    def test_calc_group_votes_equal_potential_voters_respected(self):
        self.group_one.votes = 6
        self.group_one.save()
        self.meeting.remove_roles(self.one, ROLE_POTENTIAL_VOTER)
        self.assertEqual(
            {self.two.pk: 3, self.three.pk: 3},
            self._fut(meeting=self.meeting),
        )

    def test_calc_group_votes_equal_unequal_votes(self):
        self.group_one.votes = 3
        self.group_one.save()
        self.group_two.votes = 2
        self.group_two.save()
        self.assertEqual(
            {self.one.pk: 2, self.two.pk: 2, self.three.pk: 1},
            self._fut(meeting=self.meeting, seed=1337),
        )

    def test_calc_group_votes_equal_filter(self):
        self.group_one.votes = 2
        self.group_one.save()
        users_qs = User.objects.filter(pk=self.one.pk)
        self.assertEqual(
            {self.one.pk: 2},
            self._fut(meeting=self.meeting, only_users_qs=users_qs),
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
            self._fut(meeting=self.meeting),
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
            self._fut(meeting=self.meeting, only_users_qs=users_qs),
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

    def test_delegated(self):
        self.group_one.votes = 6
        self.group_one.members.set([self.one])
        self.group_one.save()
        self.group_two.votes = 6
        self.group_two.members.set([self.two, self.three])
        self.group_two.delegate_to = self.group_one
        self.group_two.save()
        self.assertEqual(
            {self.one.pk: 12},
            self._fut(meeting=self.meeting),
        )

    def test_delegate_with_votes_none(self):
        self.group_one.votes = 6
        self.group_one.members.set([self.one])
        self.group_one.save()
        self.group_two.votes = None
        self.group_two.members.set([self.two, self.three])
        self.group_two.delegate_to = self.group_one
        self.group_two.save()
        self.assertEqual(
            {self.one.pk: 6},
            self._fut(meeting=self.meeting),
        )

    def test_delegate_with_votes_receving_none(self):
        self.group_one.votes = None
        self.group_one.members.set([self.one])
        self.group_one.save()
        self.group_two.votes = 3
        self.group_two.members.set([self.two, self.three])
        self.group_two.delegate_to = self.group_one
        self.group_two.save()
        self.assertEqual(
            {self.one.pk: 3},
            self._fut(meeting=self.meeting),
        )
