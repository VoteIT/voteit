from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase
from voteit.components.app.components.message import FlashMessage
from voteit.components.app.components.proposal_print import ProposalPrint
from voteit.meeting.models import Meeting

User = get_user_model()


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
        from voteit.components.rest_api.serializers import MeetingComponentSerializer

        return MeetingComponentSerializer

    def test_serialize_print(self):
        serializer = self._cut(self.print_component)
        self.assertEqual(
            {
                "enabled": False,
                "pk": self.print_component.pk,
                "meeting": self.meeting.pk,
                "settings": None,
                "component_name": ProposalPrint.name,
                "is_valid": True,
            },
            serializer.data,
        )

    def test_serialize_number_bad_data(self):
        self.flash_component.settings_data = {"msg": None}
        self.flash_component.save()
        serializer = self._cut(self.flash_component)
        self.assertEqual(
            {
                "enabled": False,
                "pk": self.flash_component.pk,
                "meeting": self.meeting.pk,
                "settings": None,
                "component_name": FlashMessage.name,
                "is_valid": False,
            },
            serializer.data,
        )

    def test_serialize_bad_name(self):
        bad_component = self.meeting.components.create(component_name="jeff")
        serializer = self._cut(bad_component)
        self.assertEqual(
            {
                "enabled": False,
                "pk": bad_component.pk,
                "meeting": self.meeting.pk,
                "settings": None,
                "component_name": "jeff",
                "is_valid": False,
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

    def test_enable_without_valid_settings(self):
        component = self.meeting.components.create(component_name=FlashMessage.name)
        serializer = self._cut(component, data={"enabled": True}, partial=True)
        serializer.is_valid()
        self.assertIn("enabled", serializer.errors)

    def test_enable_with_settings_in_same_request(self):
        component = self.meeting.components.create(component_name=FlashMessage.name)
        serializer = self._cut(
            component, data={"enabled": True, "settings": {"msg": "Hi"}}, partial=True
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)


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
        cls.moderator = cls.meeting.participants.get(username="moderator")

    @property
    def _cut(self):
        from voteit.components.rest_api.serializers import (
            CreateMeetingComponentSerializer,
        )

        return CreateMeetingComponentSerializer

    def test_duplicate_not_allowed(self):
        request = RequestFactory().post("/")
        request.user = self.moderator
        serializer = self._cut(
            data={"component_name": ProposalPrint.name, "meeting": self.meeting.pk},
            context={"request": request},
        )
        serializer.is_valid()
        self.assertIn("component_name", serializer.errors)
