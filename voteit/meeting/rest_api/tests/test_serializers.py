from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase
from pydantic import BaseModel

from voteit.meeting.abcs import MeetingComponentAdapter
from voteit.meeting.app.components.message import FlashMessage
from voteit.meeting.app.components.proposal_print import ProposalPrint
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.meeting.registries import meeting_components
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


class MeetingComponentSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.print_component = cls.meeting.components.create(
            component_name=ProposalPrint.name
        )
        cls.flash_component = cls.meeting.components.create(
            component_name=FlashMessage.name, settings={"msg": "Hello"}
        )

    @property
    def _cut(self):
        from voteit.meeting.rest_api.serializers import MeetingComponentSerializer

        return MeetingComponentSerializer

    def test_serialize_print(self):
        serializer = self._cut(self.print_component)
        self.assertEqual(
            {
                "state": "off",
                "pk": self.print_component.pk,
                "meeting": self.meeting.pk,
                "settings": None,
                "component_name": ProposalPrint.name,
            },
            serializer.data,
        )

    def test_serialize_number_bad_data(self):
        self.flash_component.settings_data = {"msg": None}
        self.flash_component.save()
        serializer = self._cut(self.flash_component)
        self.assertEqual(
            {
                "state": "off",
                "pk": self.flash_component.pk,
                "meeting": self.meeting.pk,
                "settings": None,
                "component_name": FlashMessage.name,
            },
            serializer.data,
        )

    def test_serialize_bad_name(self):
        bad_component = self.meeting.components.create(component_name="jeff")
        serializer = self._cut(bad_component)
        self.assertEqual(
            {
                "state": "off",
                "pk": bad_component.pk,
                "meeting": self.meeting.pk,
                "settings": None,
                "component_name": "jeff",
            },
            serializer.data,
        )

    def test_sane_data(self):
        serializer = self._cut(
            self.flash_component, data={"settings": {"msg": "Bye"}}, partial=True
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)

    def test_bad_data(self):
        serializer = self._cut(
            self.flash_component, data={"settings": {"msg": None}}, partial=True
        )
        serializer.is_valid()
        self.assertIn("settings", serializer.errors)


class CreateMeetingComponentSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.print_component = cls.meeting.components.create(
            component_name=ProposalPrint.name
        )
        cls.flash_component = cls.meeting.components.create(
            component_name=FlashMessage.name, settings={"msg": "Hello"}
        )

    @property
    def _cut(self):
        from voteit.meeting.rest_api.serializers import CreateMeetingComponentSerializer

        return CreateMeetingComponentSerializer

    def test_duplicate_allowed(self):
        serializer = self._cut(
            data={"component_name": FlashMessage.name, "meeting": self.meeting.pk}
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)

    def test_duplicate_not_allowed(self):
        serializer = self._cut(
            data={"component_name": ProposalPrint.name, "meeting": self.meeting.pk}
        )
        serializer.is_valid()
        self.assertIn("component_name", serializer.errors)
