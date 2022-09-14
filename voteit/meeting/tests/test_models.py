from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django_fsm import TransitionNotAllowed
from pydantic import BaseModel

from voteit.meeting.abcs import MeetingComponentAdapter
from voteit.meeting.models import Meeting
from voteit.meeting.registries import meeting_components
from voteit.organisation.models import Organisation

User = get_user_model()


class MeetingTests(TestCase):
    def test_workflow_transitions(self):
        meeting: Meeting = Meeting.objects.create(er_policy_name="auto_before_poll")
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

        meeting = Meeting.objects.create(er_policy_name=AutoBeforePoll.name)
        self.assertIsInstance(meeting.er_policy, AutoBeforePoll)

    def test_get_latest_er(self):
        from voteit.poll.models import ElectoralRegister

        meeting = Meeting.objects.create()
        self.assertIsNone(meeting.get_latest_er())
        er1 = ElectoralRegister.objects.create(meeting=meeting)
        self.assertEqual(er1, meeting.get_latest_er())
        er2 = ElectoralRegister.objects.create(meeting=meeting)
        self.assertEqual(er2, meeting.get_latest_er())

    def test_get_access_policies(self):
        from voteit.access_policy.app.policies.automatic import AutomaticAccess

        meeting = Meeting.objects.create()
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
        meeting = Meeting.objects.create()
        meeting.agenda_items.create()
        meeting.archive()
        ai = meeting.agenda_items.first()
        self.assertEqual("archived", ai.state)


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

    def test_unique_with_userid(self):
        self.organisation.users.create(
            first_name="King's",
            last_name="College",
            username="the-kings",
            userid="kings-college",
        )
        group = self.MeetingGroup.objects.create(
            title="King's College", meeting=self.meetings[0]
        )
        self.assertEqual(group.groupid, "kings-college-1")


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


class NumberSchema(BaseModel):
    number: int


class NumberComponent(MeetingComponentAdapter):
    name = "mock_number"
    title = "Number"
    schema = NumberSchema


class NoneComponent(MeetingComponentAdapter):
    name = "mock_none"
    title = "None"


class MeetingComponentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # cls.moderator = User.objects.get(username="moderator")
        cls.meeting = Meeting.objects.create()
        meeting_components[NumberComponent.name] = NumberComponent
        meeting_components[NoneComponent.name] = NoneComponent
        cls.number = cls.meeting.components.create(component_name="mock_number")
        cls.none = cls.meeting.components.create(component_name="mock_none")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        meeting_components.pop(NumberComponent.name)
        meeting_components.pop(NoneComponent.name)

    def test_wf_constraint(self):
        self.none.enable()
        with self.assertRaises(TransitionNotAllowed):
            self.number.enable()
        self.number.settings = {"number": 1}
        self.number.enable()
        self.number.settings_data = {"number": "B"}
        self.number.disable()
        # Only checked on enable
        with self.assertRaises(TransitionNotAllowed):
            self.number.enable()

    def test_settings_no_schema(self):
        with self.assertRaises(ValueError):
            self.none.settings = {}
