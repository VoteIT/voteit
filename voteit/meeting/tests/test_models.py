from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from voteit.active.components import ActiveUsersComponent
from voteit.components.app.components.proposal_print import ProposalPrint
from voteit.meeting.models import GroupRole
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.organisation.models import Organisation
from voteit.poll.app.er_policies.auto_always import AutoAlways
from voteit.poll.models import Poll

User = get_user_model()


class MeetingTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)

    def test_workflow_transitions(self):
        meeting = self.meeting
        meeting.ongoing()
        meeting.upcoming()
        meeting.ongoing()
        meeting.close()
        meeting.ongoing()
        meeting.close()
        meeting.request_archiving()
        meeting.abort_archiving()
        meeting.archive()
        self.assertEqual("archived", meeting.state)

    def test_er_policy(self):
        from voteit.poll.app.er_policies.auto_before_poll import AutoBeforePoll

        self.meeting.er_policy_name = AutoBeforePoll.name
        self.meeting.save()
        self.assertIsInstance(self.meeting.er_policy, AutoBeforePoll)

    def test_get_latest_er(self):
        from voteit.poll.models import ElectoralRegister

        meeting = self.meeting
        self.assertIsNone(meeting.get_latest_er())
        er1 = ElectoralRegister.objects.create(meeting=meeting)
        self.assertEqual(er1, meeting.get_latest_er())
        er2 = ElectoralRegister.objects.create(meeting=meeting)
        self.assertEqual(er2, meeting.get_latest_er())

    def test_get_access_policies(self):
        from voteit.access_policy.app.policies.automatic import AutomaticAccess

        meeting = self.meeting
        self.assertEqual(set(), set(meeting.get_access_policies()))
        AutomaticAccess.objects.create(meeting=meeting, active=True)
        found = list(meeting.get_access_policies())
        self.assertEqual(1, len(found))
        ap_inst = found[0]
        self.assertIsInstance(ap_inst, AutomaticAccess)
        ap_inst.active = False
        ap_inst.save()
        self.assertFalse(list(meeting.get_access_policies()))
        self.assertTrue(list(meeting.get_access_policies(only_active=False)))

    def test_archive_archives_ais(self):
        meeting = self.meeting
        meeting.agenda_items.create()
        meeting.archive()
        ai = meeting.agenda_items.first()
        self.assertEqual("archived", ai.state)

    def test_valid_er_policy_guard(self):
        self.meeting.er_policy_name = None
        self.assertFalse(self.meeting.valid_er_policy_guard())
        self.meeting.er_policy_name = AutoAlways.name
        self.assertTrue(self.meeting.valid_er_policy_guard())

    def test_no_ongoing_polls_guard(self):
        meeting = self.meeting
        poll: Poll = meeting.polls.create(method_name="simple")
        self.assertTrue(meeting.no_ongoing_polls_guard())
        poll.state = "ongoing"
        poll.save()
        self.assertFalse(meeting.no_ongoing_polls_guard())

    def test_component_enabled(self):
        self.meeting.components.create(
            component_name=ActiveUsersComponent.name, enabled=True
        )
        self.meeting.components.create(component_name=ProposalPrint.name, enabled=True)
        with self.assertNumQueries(1):
            self.meeting.component_enabled(ProposalPrint.name)
        with self.assertNumQueries(0):
            self.meeting.component_enabled(ActiveUsersComponent.name)
        with self.assertNumQueries(1):
            self.meeting.component_enabled(ActiveUsersComponent.name, refresh=True)


class ManagerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create()
        cls.private_meeting = cls.organisation.meetings.create()
        cls.public_meeting = cls.organisation.meetings.create(public=True)

    def test_for_user(self):
        participant = self.private_meeting.participants.create(
            username="p", organisation=self.organisation
        )
        non_participant = User.objects.create(
            username="np", organisation=self.organisation
        )
        self.assertEqual(Meeting.objects.for_user(participant).count(), 2)
        self.assertEqual(
            Meeting.objects.for_user(participant).filter(public=False).count(), 1
        )
        self.assertEqual(Meeting.objects.for_user(non_participant).count(), 1)
        self.assertIs(Meeting.objects.for_user(non_participant).get().public, True)

    def test_distinct_for_user(self):
        User = get_user_model()
        for n in range(1, 4):
            self.public_meeting.participants.create(
                username=f"p{n}", organisation=self.organisation
            )
        participant = self.public_meeting.participants.create(
            username="p", organisation=self.organisation
        )
        self.private_meeting.participants.add(participant)
        non_participant = User.objects.create(
            username="np", organisation=self.organisation
        )
        meetings_for_p = Meeting.objects.for_user(participant)
        meetings_for_np = Meeting.objects.for_user(non_participant)
        self.assertEqual(meetings_for_p.count(), 2)
        self.assertEqual(meetings_for_np.count(), 1)
        with self.assertRaises(self.public_meeting.DoesNotExist):
            meetings_for_np.get(pk=self.private_meeting.pk)
        self.assertTrue(meetings_for_p.get(pk=self.private_meeting.pk))

    def test_matches_organisation(self):
        old_org_user = self.organisation.users.create(username="old_org_user")
        self.assertEqual(1, Meeting.objects.for_user(old_org_user).count())
        new_org = Organisation.objects.create()
        new_org_user = new_org.users.create(username="new_org_user")
        self.assertEqual(0, Meeting.objects.for_user(new_org_user).count())


class MeetingGroupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create()
        cls.meetings = [cls.organisation.meetings.create() for _ in range(2)]

    @property
    def MeetingGroup(self):
        from voteit.meeting.models import MeetingGroup

        return MeetingGroup

    def test_unique_in_group(self):
        group1 = self.meetings[0].groups.create(title="King's College")
        group2 = self.meetings[1].groups.create(title="King's College")
        group3 = self.meetings[0].groups.create(title="King's Cóllege")
        self.assertEqual(group1.groupid, "kings-college")
        self.assertEqual(group2.groupid, "kings-college")
        self.assertEqual(group3.groupid, "kings-college-1")

    def test_max_votes_and_membership(self):
        meeting = self.meetings[0]
        group = meeting.groups.create(title="Voters", votes=3)
        voter_one = self.organisation.users.create(username="one")
        voter_two = self.organisation.users.create(username="two")
        member_one = group.memberships.create(user=voter_one, votes=1)
        group.memberships.create(user=voter_two, votes=1)
        group.votes = 2
        group.save()
        member_one.refresh_from_db()
        self.assertEqual(1, member_one.votes)
        group.votes = 1
        group.save()
        member_one.refresh_from_db()
        self.assertIsNone(member_one.votes)

    def test_relation_to_self(self):
        group = self.meetings[0].groups.create(title="One")
        group.delegate_to = group
        with self.assertRaises(IntegrityError):
            group.save()

    # FIXME: Would be great with a db constraint, but rest serializer takes care of this too
    # def test_relation_to_group_from_other_meeting(self):
    #     group_one = self.meetings[0].groups.create(title="one")
    #     group_two = self.meetings[1].groups.create(title="two")
    #     group_one.delegate_to = group_two
    #     with self.assertRaises(IntegrityError):
    #         group_one.save()
    #
    # def test_relation_delegate_when_already_delegated_to(self):
    #     delegator = self.meetings[0].groups.create(title="delegator")
    #     receiver = self.meetings[0].groups.create(title="receiver")
    #     receiver.delegate_to = delegator
    #     receiver.save()
    #     delegator.delegate_to = receiver
    #     with self.assertRaises(IntegrityError):
    #         delegator.save()
    #
    # def test_relation_delegate_when_receiver_delegates(self):
    #     receiver = self.meetings[0].groups.create(title="Receiver")
    #     first_delegator = self.meetings[0].groups.create(title="First")
    #     second_delegator = self.meetings[0].groups.create(title="Second")
    #     first_delegator.delegate_to = receiver
    #     first_delegator.save()
    #     second_delegator.delegate_to = first_delegator
    #     with self.assertRaises(IntegrityError):
    #         second_delegator.save()


class MeetingRolesTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.meeting = Meeting.objects.get(pk=1)

    @property
    def _cut(self):
        from voteit.meeting.models import MeetingRoles

        return MeetingRoles

    def test_unique_constraint(self):
        with self.assertRaises(IntegrityError):
            self._cut.objects.create(user=self.moderator, context=self.meeting)


class GroupRoleTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.meeting.group_roles_active = True
        cls.meeting.save()
        cls.group_one = cls.meeting.groups.create(title="Oners")
        cls.group_two = cls.meeting.groups.create(title="Twoers")
        cls.participant = User.objects.get(username="participant")
        cls.councilor = GroupRole.objects.create(
            meeting=cls.meeting,
            roles=[ROLE_POTENTIAL_VOTER, ROLE_DISCUSSER, ROLE_PROPOSER],
            title="Councilor",
        )
        cls.debater = GroupRole.objects.create(
            meeting=cls.meeting, roles=[ROLE_DISCUSSER], title="Debater"
        )

    def assertRoles(self, expected: set[str] | list[str], value: set):
        self.assertEqual({ROLE_PARTICIPANT} | set(expected), value)

    def test_assign_role_via_create(self):
        self.assertEqual(
            {ROLE_PARTICIPANT},
            self.meeting.get_roles(self.participant),
        )
        self.group_one.memberships.create(user=self.participant, role=self.councilor)
        self.assertRoles(self.councilor.roles, self.meeting.get_roles(self.participant))

    def test_several_groups_keeps_role_intact(self):
        self.group_one.memberships.create(user=self.participant, role=self.councilor)
        second = self.group_two.memberships.create(
            user=self.participant, role=self.councilor
        )
        # And deleting it keeps original
        second.delete()
        self.assertRoles(self.councilor.roles, self.meeting.get_roles(self.participant))

    def test_delete_group(self):
        self.group_one.memberships.create(user=self.participant, role=self.councilor)
        self.assertRoles(self.councilor.roles, self.meeting.get_roles(self.participant))
        self.group_one.delete()
        self.assertRoles(set(), self.meeting.get_roles(self.participant))

    def test_group_roles_disabled_adjust_roles(self):
        self.group_one.memberships.create(user=self.participant, role=self.debater)
        self.assertRoles(self.debater.roles, self.meeting.get_roles(self.participant))
        self.meeting.group_roles_active = False
        self.meeting.save()
        self.debater.roles = [ROLE_POTENTIAL_VOTER]
        self.debater.save()
        self.assertRoles([ROLE_DISCUSSER], self.meeting.get_roles(self.participant))

    def test_deleting_group_role_keeps_membership(self):
        self.group_one.memberships.create(user=self.participant, role=self.debater)
        self.assertRoles(self.debater.roles, self.meeting.get_roles(self.participant))
        self.debater.delete()
        self.assertTrue(self.group_one.memberships.filter(user=self.participant))
