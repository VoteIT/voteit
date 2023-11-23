from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import override_settings
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from voteit.meeting.models import GroupMembership
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.models import MeetingRoles
from voteit.meeting.rest_api.serializers import CreateGroupMembershipSerializer
from voteit.meeting.rest_api.serializers import CreateMeetingGroupSerializer
from voteit.meeting.rest_api.serializers import GroupMembershipSerializer
from voteit.meeting.rest_api.serializers import GroupRoleSerializer
from voteit.meeting.rest_api.serializers import MeetingGroupSerializer
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.tests.fixtures import DIALECT_FIXTURES
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
            {ROLE_PARTICIPANT, ROLE_MODERATOR},
            set(serializer.data["current_user_roles"]),
        )

    def test_participant(self):
        request = self._mk_request(self.participant)
        serializer = self._cut(self.meeting, context={"request": request})
        self.assertEqual({ROLE_PARTICIPANT}, set(serializer.data["current_user_roles"]))


@override_settings(MEETING_DIALECTS_DIR=DIALECT_FIXTURES)
class CreateMeetingSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    def setUp(self):
        self.moderator = User.objects.get(username="moderator")

    @property
    def _cut(self):
        from voteit.meeting.rest_api.serializers import CreateMeetingSerializer

        return CreateMeetingSerializer

    def _mk_one(self, **kwargs):
        rf = RequestFactory()
        request = rf.get("/")
        request.user = self.moderator
        kwargs.setdefault("title", "Hello world")
        return self._cut(
            data=kwargs,
            context={"request": request},
        )

    def test_create(self):
        serializer = self._mk_one()
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        instance = serializer.save()
        self.assertIsInstance(instance, Meeting)
        self.assertEqual(self.moderator, instance.author)

    def test_create_install_dialect(self):
        serializer = self._mk_one(install_dialect="two")
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        instance = serializer.save()
        self.assertIsInstance(instance, Meeting)
        self.assertEqual("two", instance.installed_dialect)

    def test_create_install_dialect_not_installable(self):
        serializer = self._mk_one(install_dialect="one")
        serializer.is_valid()
        self.assertIn("install_dialect", serializer.errors)

    def test_create_install_dialect_bad_name(self):
        serializer = self._mk_one(install_dialect="404")
        serializer.is_valid()
        self.assertIn("install_dialect", serializer.errors)

    def test_create_emtpy_er_name(self):
        serializer = self._mk_one(er_policy_name="")
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        instance = serializer.save()
        self.assertIsNone(instance.er_policy_name)


@override_settings(MEETING_DIALECTS_DIR=DIALECT_FIXTURES)
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

    def test_installed_dialect(self):
        request = self._mk_request(self.moderator)
        serializer = self._cut(self.meeting, context={"request": request})
        self.assertEqual(None, serializer.data["installed_dialect"])
        self.meeting.installed_dialect = "three"
        serializer = self._cut(self.meeting, context={"request": request})
        self.assertEqual("three", serializer.data["installed_dialect"])
        self.assertEqual(
            {
                "description": "",
                "group_roles_active": True,
                "installable": True,
                "name": "three",
                "requires": ["one", "two"],
                "title": "Three",
                "view_components": {},
                "groups_can_delegate": False,
                "groups": [
                    {"groupid": "pirates"},
                    {"groupid": "swashbucklers"},
                    {"groupid": "shiphands"},
                ],
            },
            serializer.data["dialect"],
        )


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
        self.assertEqual({ROLE_PARTICIPANT, ROLE_MODERATOR}, set(data["assigned"]))
        self.assertEqual(
            {
                "pk": 1,
                "userid": "moderator",
                "email": "moderator@voteit.se",
                "first_name": "Moderator",
                "last_name": "",
                "img_url": None,
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
        cls.mod_member = cls.moderator_club.memberships.create(
            user=cls.moderator, role=cls.group_role
        )
        cls.pleb_member = cls.plebei_hangout.memberships.create(user=cls.participant)

    def _mk_request(self, user):
        rf = RequestFactory()
        request = rf.get("/")
        request.user = user
        return request

    def test_meeting_group(self):
        data = MeetingGroupSerializer(self.moderator_club).data
        self.assertEqual(self.moderator_club.pk, data.pop("pk"))
        self.assertEqual("", data.pop("body"))
        self.assertEqual([], data.pop("tags"))
        self.assertEqual("Moderator club", data.pop("title"))
        self.assertEqual("modclub", data.pop("groupid"))
        self.assertEqual(0, data.pop("votes"))
        self.assertEqual(self.meeting.pk, data.pop("meeting"))
        self.assertEqual(None, data.pop("delegate_to"))
        self.assertFalse(data.keys())

    def test_meeting_group_many(self):
        data = MeetingGroupSerializer(
            [self.moderator_club, self.plebei_hangout], many=True
        ).data
        self.assertEqual(2, len(data))

    def test_create_meeting_group_many(self):
        counted = self.meeting.groups.count()
        serializer = CreateMeetingGroupSerializer(
            data=[
                {"title": "One", "votes": "1", "meeting": self.meeting.pk},
                {"title": "Two", "meeting": self.meeting.pk},
            ],
            many=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        self.assertEqual(counted + 2, self.meeting.groups.count())

    def test_create_meeting_group(self):
        serializer = CreateMeetingGroupSerializer(
            data={
                "title": "New",
                "groupid": "new_id",
                "votes": "1",
                "meeting": self.meeting.pk,
            }
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        instance = serializer.save()
        self.assertIsInstance(instance, MeetingGroup)
        self.assertEqual("new_id", instance.groupid)

    def test_patch_meeting_group(self):
        serializer = MeetingGroupSerializer(
            self.plebei_hangout,
            data={
                "groupid": "new_id",
            },
            partial=True,
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertEqual("new_id", self.plebei_hangout.groupid)

    def test_create_meeting_group_existing_groupid(self):
        serializer = CreateMeetingGroupSerializer(
            data={
                "title": "New",
                "groupid": self.plebei_hangout.groupid,
                "votes": "1",
                "meeting": self.meeting.pk,
            }
        )
        serializer.is_valid()
        self.assertIn("groupid", serializer.errors)

    def test_create_meeting_group_bad_groupid(self):
        serializer = CreateMeetingGroupSerializer(
            data={
                "title": "New",
                "groupid": "Äöl",
                "votes": "1",
                "meeting": self.meeting.pk,
            }
        )
        serializer.is_valid()
        self.assertIn("groupid", serializer.errors)
        serializer = CreateMeetingGroupSerializer(
            data={
                "title": "New",
                "groupid": " A ",
                "votes": "1",
                "meeting": self.meeting.pk,
            }
        )
        serializer.is_valid()
        self.assertIn("groupid", serializer.errors)

    def test_patch_meeting_group_existing_groupid(self):
        serializer = MeetingGroupSerializer(
            self.plebei_hangout,
            data={"groupid": self.moderator_club.groupid},
            partial=True,
        )
        serializer.is_valid()
        self.assertIn("groupid", serializer.errors)
        # Same ok
        serializer = MeetingGroupSerializer(
            self.plebei_hangout,
            data={"groupid": self.plebei_hangout.groupid},
            partial=True,
        )
        serializer.is_valid()
        self.assertNotIn("groupid", serializer.errors)

    def test_patch_meeting_group_bad_groupid(self):
        serializer = MeetingGroupSerializer(
            self.plebei_hangout,
            data={"groupid": "ö"},
            partial=True,
        )
        serializer.is_valid()
        self.assertIn("groupid", serializer.errors)
        serializer = MeetingGroupSerializer(
            self.plebei_hangout,
            data={"groupid": " A"},
            partial=True,
        )
        serializer.is_valid()
        self.assertIn("groupid", serializer.errors)

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
        self.assertIsNone(data.pop("votes"))
        self.assertFalse(data.keys())

    def test_group_member_many(self):
        data = GroupMembershipSerializer(
            [self.pleb_member, self.mod_member], many=True
        ).data
        self.assertEqual(2, len(data))

    def test_group_membership_create(self):
        serializer = CreateGroupMembershipSerializer(
            data={"meeting_group": self.plebei_hangout.pk, "user": self.moderator.pk},
            context={"request": self._mk_request(self.moderator)},
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        instance = serializer.save()
        self.assertIsInstance(instance, GroupMembership)

    def test_group_membership_create_role_not_same_meeting(self):
        new_meeting = Meeting.objects.create()
        new_role = new_meeting.group_roles.create(title="New role", role_id="thenew")
        serializer = CreateGroupMembershipSerializer(
            data={
                "meeting_group": self.plebei_hangout.pk,
                "user": self.moderator.pk,
                "role": new_role.pk,
            },
            context={"request": self._mk_request(self.moderator)},
        )
        serializer.is_valid()
        self.assertIn("role", serializer.errors)

    def test_group_membership_patch_role_not_same_meeting(self):
        new_meeting = Meeting.objects.create()
        new_role = new_meeting.group_roles.create(title="New role", role_id="thenew")
        serializer = CreateGroupMembershipSerializer(
            data={
                "meeting_group": self.plebei_hangout.pk,
                "user": self.moderator.pk,
            },
            context={"request": self._mk_request(self.moderator)},
        )
        serializer.is_valid()
        instance = serializer.save()
        serializer = GroupMembershipSerializer(
            instance,
            data={"role": new_role.pk},
            context={"request": self._mk_request(self.moderator)},
            partial=True,
        )
        serializer.is_valid()
        self.assertIn("role", serializer.errors)

    def test_group_membership_create_user_not_same_meeting(self):
        new_meeting = Meeting.objects.create()
        new_group = new_meeting.groups.create(title="New group", groupid="thenew")
        serializer = CreateGroupMembershipSerializer(
            data={
                "meeting_group": new_group.pk,
                "user": self.moderator.pk,
            },
            context={"request": self._mk_request(self.moderator)},
        )
        serializer.is_valid()
        self.assertIn("user", serializer.errors)

    def test_group_membership_create_duplicate(self):
        serializer = CreateGroupMembershipSerializer(
            data={
                "meeting_group": self.plebei_hangout.pk,
                "user": self.participant.pk,
            },
            context={"request": self._mk_request(self.moderator)},
        )
        serializer.is_valid()
        self.assertTrue(serializer.errors)
