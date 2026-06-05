from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.meeting.models import GroupMembership
from voteit.meeting.models import MeetingGroup
from voteit.poll.app.er_policies.group_votes_before_poll import GroupVotesBeforePoll
from voteit.poll.exceptions import ElectoralRegisterError
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

User = get_user_model()


class GroupVotesBeforePollTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            er_policy_name=GroupVotesBeforePoll.name,
            group_votes_active=True,
            state="ongoing",
        )
        # cls.ai = cls.meeting.agenda_items.create()
        cls.user1 = User.objects.create(username="one")
        cls.user2 = User.objects.create(username="two")
        cls.meeting.add_roles(cls.user1, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.user2, ROLE_POTENTIAL_VOTER)
        cls.group_l: MeetingGroup = cls.meeting.groups.create(title="Large", votes=10)
        cls.group_s: MeetingGroup = cls.meeting.groups.create(title="Small", votes=1)
        cls.mem_one_l: GroupMembership = cls.group_l.memberships.create(
            user=cls.user1, votes=5
        )
        cls.mem_two_l: GroupMembership = cls.group_l.memberships.create(
            user=cls.user2, votes=5
        )
        cls.mem_one_s: GroupMembership = cls.group_s.memberships.create(
            user=cls.user1, votes=1
        )
        cls.poll: Poll = cls.meeting.polls.create(method_name="simple")

    def setUp(self):
        self.meeting.refresh_from_db()
        self.poll.refresh_from_db()

    def test_get_voters(self):
        self.assertEqual(
            {self.user1.pk: 6, self.user2.pk: 5}, self.meeting.er_policy.get_voters()
        )
        self.group_s.votes = None  # Will nuke assigned votes
        self.group_s.save()
        self.assertEqual(
            {self.user1.pk: 5, self.user2.pk: 5}, self.meeting.er_policy.get_voters()
        )

    def test_get_voters_invalid_count(self):
        self.mem_one_s.votes = 10  # More than group has
        self.mem_one_s.save()
        with self.assertRaises(ElectoralRegisterError):
            self.meeting.er_policy.get_voters()

    def test_get_voters_wrong_meeting_setting(self):
        self.meeting.group_votes_active = False
        self.meeting.save()
        with self.assertRaises(ElectoralRegisterError):
            self.meeting.er_policy.create_er()

    def test_new_er_on_ongoing(self):
        ai = self.meeting.agenda_items.create()
        self.poll.proposals.create(agenda_item=ai)
        self.poll.ongoing(force=True)
        self.assertIsInstance(self.poll.electoral_register, ElectoralRegister)
        self.assertEqual(
            {self.user1.pk: 6, self.user2.pk: 5},
            self.poll.electoral_register.get_weight_dict(),
        )

    def test_gm_votes_cleared_when_pv_role_removed(self):
        self.assertEqual(5, self.mem_two_l.votes)
        self.meeting.remove_roles(self.user2, ROLE_POTENTIAL_VOTER)
        self.mem_two_l.refresh_from_db()
        self.assertIsNone(self.mem_two_l.votes)

    def test_changed_er_ref_on_poll(self):
        ai = self.meeting.agenda_items.create()
        first_er = self.meeting.er_policy.create_er()
        self.poll.electoral_register = first_er
        self.mem_one_s.votes = 0
        self.mem_one_s.save()
        self.poll.proposals.create(agenda_item=ai)
        self.poll.ongoing(force=True)
        self.assertNotEqual(first_er, self.poll.electoral_register)
        self.assertEqual(
            {self.user1.pk: 5, self.user2.pk: 5},
            self.poll.electoral_register.get_weight_dict(),
        )

    def test_no_groups(self):
        self.meeting.groups.all().delete()
        self.assertIsNone(self.meeting.er_policy.create_er())
