from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.active.components import ActiveUsersComponent
from voteit.meeting.models import GroupMembership
from voteit.meeting.models import GroupRole
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.app.er_policies.main_or_subst_er import MAIN_ROLE_ID
from voteit.poll.app.er_policies.main_or_subst_er import MainSubstActivePolicy
from voteit.poll.app.er_policies.main_or_subst_er import SUBSTITUTE_ROLE_ID

User = get_user_model()


class MainSubstActivePolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            er_policy_name=MainSubstActivePolicy.name,
            group_roles_active=True,
        )
        # Roles
        cls.main_role: GroupRole = cls.meeting.group_roles.create(
            role_id=MAIN_ROLE_ID,
            roles=[ROLE_POTENTIAL_VOTER],
        )
        cls.subst_role: GroupRole = cls.meeting.group_roles.create(
            role_id=SUBSTITUTE_ROLE_ID,
            roles=[ROLE_POTENTIAL_VOTER],
        )
        # Groups
        cls.the_voters_group: MeetingGroup = cls.meeting.groups.create(
            groupid="the_voters", votes=2
        )
        cls.the_other_voters_group: MeetingGroup = cls.meeting.groups.create(
            groupid="the_other_voters", votes=2
        )
        cls.the_board: MeetingGroup = cls.meeting.groups.create(groupid="board")
        # Users
        cls.president = User.objects.create(username="president")
        cls.main1 = User.objects.create(username="one")
        cls.main2 = User.objects.create(username="two")
        cls.subst3 = User.objects.create(username="three")
        cls.subst4 = User.objects.create(username="four")
        users = [cls.president, cls.main1, cls.main2, cls.subst3, cls.subst4]
        for user in users:
            cls.meeting.add_roles(user, ROLE_PARTICIPANT)
        # Memberships
        cls.mem_president: GroupMembership = cls.the_board.memberships.create(
            user=cls.president,
        )
        cls.mem_one: GroupMembership = cls.the_voters_group.memberships.create(
            user=cls.main1, role=cls.main_role
        )
        cls.mem_two: GroupMembership = cls.the_voters_group.memberships.create(
            user=cls.main2, role=cls.main_role
        )
        cls.mem_three: GroupMembership = cls.the_voters_group.memberships.create(
            user=cls.subst3, role=cls.subst_role
        )
        cls.mem_four: GroupMembership = cls.the_voters_group.memberships.create(
            user=cls.subst4, role=cls.subst_role
        )
        # Enable active component
        cls.component = cls.meeting.components.create(
            component_name=ActiveUsersComponent.name, enabled=True
        )
        # Set active users
        for user in users:
            cls.meeting.active_users.create(user=user)

    def test_simple(self):
        self.assertEqual(
            {self.main1.pk: 1, self.main2.pk: 1}, self.meeting.er_policy.get_voters()
        )

    def test_simple_with_disabled_active(self):
        self.component.delete()
        self.assertEqual(
            {self.main1.pk: 1, self.main2.pk: 1}, self.meeting.er_policy.get_voters()
        )
        self.the_voters_group.votes = 5
        self.the_voters_group.save()
        self.assertEqual(
            {self.main1.pk: 1, self.main2.pk: 1, self.subst3.pk: 1, self.subst4.pk: 1},
            self.meeting.er_policy.get_voters(),
        )

    def test_n1(self):
        for i in range(5):
            group = self.meeting.groups.create(groupid=f"group_{i}", votes=3)
            user = self.meeting.participants.create(username=f"user_{i}")
            group.memberships.create(user=user, role=self.main_role)
        with self.assertNumQueries(5):
            self.meeting.er_policy.get_voters()

    def test_more_votes_than_users(self):
        self.the_voters_group.votes = 10
        self.the_voters_group.save()
        self.assertEqual(
            {self.main1.pk: 1, self.main2.pk: 1, self.subst3.pk: 1, self.subst4.pk: 1},
            self.meeting.er_policy.get_voters(),
        )

    def test_active_order_matters(self):
        self.meeting.active_users.filter(user=self.main2).delete()
        self.assertEqual(
            {self.main1.pk: 1, self.subst3.pk: 1},
            self.meeting.er_policy.get_voters(),
        )

    def test_memberships_updated_with_votes(self):
        self.meeting.er_policy.get_voters()
        self.assertEqual(0, GroupMembership.objects.filter(votes__gt=0).count())
        self.meeting.er_policy.get_voters(update_memberships=True)
        self.assertEqual(2, GroupMembership.objects.filter(votes__gt=0).count())

    def test_correct_memberships_updated(self):
        new_group = self.meeting.groups.create(votes=2)
        new_group.memberships.create(user=self.subst3, role=self.main_role)
        GroupMembership.objects.all().update(votes=2)
        self.assertEqual(6, GroupMembership.objects.filter(votes=2).count())
        self.assertEqual(
            {self.main1.pk: 1, self.main2.pk: 1, self.subst3.pk: 1},
            self.meeting.er_policy.get_voters(update_memberships=True),
        )
        self.assertEqual(
            [self.main1.pk, self.main2.pk, self.subst3.pk],
            list(
                GroupMembership.objects.filter(votes__gt=0)
                .order_by("pk")
                .values_list("user_id", flat=True)
            ),
        )
