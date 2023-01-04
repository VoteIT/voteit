from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.meeting.rest_api.serializers import GroupMembershipSerializer
from voteit.meeting.rest_api.serializers import GroupRoleSerializer
from voteit.meeting.rest_api.serializers import MeetingGroupSerializer
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.app.er_policies.auto_always import AutoAlways
from voteit.poll.app.polls.simple import Simple

User = get_user_model()


class MeetingSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    def setUp(self):
        self.meeting = Meeting.objects.get(pk=1)
        self.participant = User.objects.get(username="participant")
        self.moderator = User.objects.get(username="moderator")

    @property
    def _cut(self):
        from voteit.meeting.rest_api.serializers import MeetingSerializer

        return MeetingSerializer

    def _mk_request(self, user):
        rf = RequestFactory()
        request = rf.get("/")
        request.user = user
        return request

    def test_roles_moderator(self):
        request = self._mk_request(self.moderator)
        serializer = self._cut(self.meeting, context={"request": request})
        self.assertEqual(
            {"participant", "moderator"}, set(serializer.data["current_user_roles"])
        )

    def test_participant(self):
        request = self._mk_request(self.participant)
        serializer = self._cut(self.meeting, context={"request": request})
        self.assertEqual({"participant"}, set(serializer.data["current_user_roles"]))


class MeetingDetailSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    def setUp(self):
        self.meeting = Meeting.objects.get(pk=1)
        self.participant = User.objects.get(username="participant")
        self.moderator = User.objects.get(username="moderator")

    @property
    def _cut(self):
        from voteit.meeting.rest_api.serializers import MeetingDetailSerializer

        return MeetingDetailSerializer

    def _mk_request(self, user):
        rf = RequestFactory()
        request = rf.get("/")
        request.user = user
        return request

    def test_create(self):
        request = self._mk_request(self.participant)
        serializer = self._cut(
            data={"title": "Hello", "er_policy_name": AutoAlways.name},
            context={"request": request},
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        instance = serializer.save()
        self.assertIsInstance(instance, Meeting)

    def test_update_er_policy(self):
        request = self._mk_request(self.participant)
        serializer = self._cut(
            self.meeting,
            data={"title": "Hello", "er_policy_name": AutoAlways.name},
            context={"request": request},
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        serializer.save()
        # breakpoint()
        self.assertEqual(AutoAlways.name, self.meeting.er_policy_name)

    def test_update_er_policy_ongoing_polls(self):
        self.meeting.polls.create(state="ongoing", method_name=Simple.name)
        request = self._mk_request(self.participant)
        serializer = self._cut(
            self.meeting,
            data={"title": "Hello", "er_policy_name": AutoAlways.name},
            context={"request": request},
        )
        serializer.is_valid()
        self.assertIn("er_policy_name", serializer.errors)


class MeetingRolesSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @property
    def _cut(self):
        from voteit.meeting.rest_api.serializers import MeetingRolesSerializer

        return MeetingRolesSerializer

    def test_moderator(self):
        instance = MeetingRoles.objects.get(pk=1)
        serializer = self._cut(instance)
        data = serializer.data
        self.assertEqual({"participant", "moderator"}, set(data["assigned"]))
        self.assertEqual(
            {
                "pk": 1,
                "userid": "moderator",
                "email": "moderator@voteit.se",
                "first_name": "Moderator",
                "full_name": "Moderator",
                "last_name": "",
                "img_url": None,
                "organisation": 1,
                "state": "incomplete",
            },
            dict(data["user"]),
        )
        self.assertEqual(1, data["meeting"])
        self.assertEqual(1, data["pk"])

    def test_prefetch(self):
        qs = MeetingRoles.objects.prefetch_related("user")
        serializer = self._cut(instance=qs, many=True)
        with self.assertNumQueries(2):
            data = serializer.data


class MeetingGroupRelatedSerializersTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.group_role = cls.meeting.group_roles.create(
            title="Supreme leader", role_id="leader", roles=[ROLE_POTENTIAL_VOTER]
        )
        cls.moderator_club = cls.meeting.groups.create(
            title="Moderator club", groupid="modclub", votes=0
        )
        cls.plebei_hangout = cls.meeting.groups.create(
            title="The hangout", groupid="plebei"
        )
        cls.mod_member = cls.moderator_club.role_assignments.create(
            user=cls.moderator, role=cls.group_role
        )
        cls.pleb_member = cls.plebei_hangout.role_assignments.create(
            user=cls.participant
        )

    def test_meeting_group(self):
        data = MeetingGroupSerializer(self.moderator_club).data
        self.assertEqual(self.moderator_club.pk, data.pop("pk"))
        self.assertEqual("", data.pop("body"))
        self.assertIsNotNone(data.pop("created"))
        self.assertIsNotNone(data.pop("modified"))
        self.assertEqual([], data.pop("tags"))
        self.assertEqual("Moderator club", data.pop("title"))
        self.assertEqual("modclub", data.pop("groupid"))
        self.assertEqual(0, data.pop("votes"))
        self.assertEqual(None, data.pop("author"))
        self.assertEqual(None, data.pop("last_modified_by"))
        self.assertEqual(self.meeting.pk, data.pop("meeting"))
        self.assertFalse(data.keys())

    def test_meeting_group_many(self):
        data = MeetingGroupSerializer(
            [self.moderator_club, self.plebei_hangout], many=True
        ).data
        self.assertEqual(2, len(data))

    def test_group_role(self):
        data = GroupRoleSerializer(self.group_role).data
        self.assertEqual(self.group_role.pk, data.pop("pk"))
        self.assertEqual("Supreme leader", data.pop("title"))
        self.assertEqual("leader", data.pop("role_id"))
        self.assertFalse(data.pop("can_propose_as"))
        self.assertFalse(data.pop("can_discuss_as"))
        self.assertEqual([ROLE_POTENTIAL_VOTER], data.pop("roles"))
        self.assertEqual(self.meeting.pk, data.pop("meeting"))
        self.assertFalse(data.keys())

    def test_group_role_many(self):
        data = GroupRoleSerializer([self.group_role], many=True).data
        self.assertEqual(1, len(data))

    def test_group_member(self):
        data = GroupMembershipSerializer(self.mod_member).data
        self.assertEqual(self.mod_member.pk, data.pop("pk"))
        self.assertEqual(self.moderator.pk, data.pop("user"))
        self.assertEqual(self.moderator_club.pk, data.pop("meeting_group"))
        self.assertEqual(self.group_role.pk, data.pop("role"))
        self.assertFalse(data.keys())

    def test_group_member_many(self):
        data = GroupMembershipSerializer(
            [self.pleb_member, self.mod_member], many=True
        ).data
        self.assertEqual(2, len(data))
