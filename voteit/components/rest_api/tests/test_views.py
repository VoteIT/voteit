from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase
from voteit.components.app.components.message import FlashMessage
from voteit.components.app.components.proposal_print import ProposalPrint
from voteit.meeting.models import Meeting

User = get_user_model()


class MeetingComponentViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.outsider = User.objects.create(username="outsider")
        cls.print_component = cls.meeting.components.create(
            component_name=ProposalPrint.name
        )
        cls.message_component = cls.meeting.components.create(
            component_name=FlashMessage.name, settings={"msg": "Hello"}
        )

    def test_moderator_list(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-components-list")
        response = self.client.get(url, data={"meeting": 1})
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(2, len(data))

    def test_moderator_list_empty_filter(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-components-list")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertFalse(response.json())

    def test_with_filter_participant(self):
        self.client.force_login(self.participant)
        url = reverse("meeting-components-list")
        response = self.client.get(url, data={"meeting": 1})
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(2, len(data))

    def test_with_filter_outsider(self):
        self.client.force_login(self.outsider)
        url = reverse("meeting-components-list")
        response = self.client.get(url, data={"meeting": 1})
        self.assertEqual(404, response.status_code)

    def test_create_moderator(self):
        self.print_component.delete()
        self.client.force_login(self.moderator)
        url = reverse("meeting-components-list")
        response = self.client.post(
            url, data={"meeting": 1, "component_name": ProposalPrint.name}
        )
        self.assertEqual(201, response.status_code)
        data = response.json()
        self.assertTrue(data.pop("pk"))
        self.assertEqual(
            {
                "component_name": ProposalPrint.name,
                "meeting": 1,
                "settings": None,
                "state": "off",
            },
            data,
        )

    def test_create_duplicate_name(self):
        self.client.force_login(self.moderator)
        url = reverse("meeting-components-list")
        response = self.client.post(
            url, data={"meeting": 1, "component_name": ProposalPrint.name}
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("component_name", response.json())

    def test_create_participant(self):
        self.print_component.delete()
        self.client.force_login(self.participant)
        url = reverse("meeting-components-list")
        response = self.client.post(
            url, data={"meeting": 1, "component_name": ProposalPrint.name}
        )
        self.assertEqual(403, response.status_code)

    def test_patch_moderator(self):
        self.client.force_login(self.moderator)
        url = reverse(
            "meeting-components-detail", kwargs={"pk": self.print_component.pk}
        )
        response = self.client.patch(
            url, data={"meeting": 2, "component_name": "blaha", "settings": None}
        )
        self.assertEqual(200, response.status_code)
        data = response.json()
        # Nothing changed
        self.assertEqual(
            {
                "component_name": ProposalPrint.name,
                "meeting": 1,
                "settings": None,
                "state": "off",
                "pk": self.print_component.pk,
                "is_valid": True,
            },
            data,
        )

    def test_patch_moderator_with_bad_settings(self):
        self.client.force_login(self.moderator)
        url = reverse(
            "meeting-components-detail", kwargs={"pk": self.print_component.pk}
        )
        response = self.client.patch(
            url, data={"meeting": 2, "component_name": "blaha", "settings": {}}
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("settings", response.json())

    def test_patch_participant(self):
        self.client.force_login(self.participant)
        url = reverse(
            "meeting-components-detail", kwargs={"pk": self.print_component.pk}
        )
        response = self.client.patch(
            url, data={"meeting": 2, "component_name": "blaha", "settings": {}}
        )
        self.assertEqual(403, response.status_code)

    def test_delete_moderator(self):
        self.client.force_login(self.moderator)
        url = reverse(
            "meeting-components-detail", kwargs={"pk": self.print_component.pk}
        )
        response = self.client.delete(url)
        self.assertEqual(204, response.status_code)

    def test_delete_participant(self):
        self.client.force_login(self.participant)
        url = reverse(
            "meeting-components-detail", kwargs={"pk": self.print_component.pk}
        )
        response = self.client.delete(url)
        self.assertEqual(403, response.status_code)

    def test_transition_moderator(self):
        self.client.force_login(self.moderator)
        url = reverse(
            "meeting-components-transitions", kwargs={"pk": self.print_component.pk}
        )
        response = self.client.post(url, data={"transition": "enable"})
        self.assertEqual(201, response.status_code)

    def test_get_print_moderator(self):
        self.client.force_login(self.moderator)
        url = reverse(
            "meeting-components-detail", kwargs={"pk": self.print_component.pk}
        )
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertIsNone(data["schema"])

    def test_get_message_moderator(self):
        self.client.force_login(self.moderator)
        url = reverse(
            "meeting-components-detail", kwargs={"pk": self.message_component.pk}
        )
        response = self.client.get(url, data={"transition": "enable"})
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(self.message_component.adapter.schema.schema(), data["schema"])
