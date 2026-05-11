from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from envelope.testing import testing_channel_layers_setting
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase
from django.test.utils import override_settings

from voteit.meeting.models import Meeting

if TYPE_CHECKING:
    from voteit.core.models import User as UserType

User: UserType = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class NoteViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.participant: UserType = User.objects.get(username="participant")
        cls.moderator: UserType = User.objects.get(username="moderator")
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.note = cls.participant.notes.create(proposal=cls.prop)
        #'Wrong' context
        cls.another_meeting = Meeting.objects.create()
        cls.another_ai = cls.another_meeting.agenda_items.create()
        cls.another_prop = cls.another_ai.proposals.create()
        cls.another_note = cls.participant.notes.create(proposal=cls.another_prop)

    def test_create(self):
        url = reverse("notes-list")
        self.client.force_login(self.participant)
        response = self.client.post(
            url,
            data={
                "proposal": self.prop2.pk,
                "body": "I <b>dig</b> this!",
                "user": self.moderator.pk,  # Removed
            },
        )
        data = response.json()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, data)
        data.pop("pk")
        data.pop("created")
        self.assertDictEqual(
            {
                "proposal": self.prop2.pk,
                "meeting": self.meeting.pk,
                "agenda_item": self.ai.pk,
                "user": self.participant.pk,
                "intent": "",
                "body": "I <b>dig</b> this!",
            },
            data,
        )

    def test_create_duplicate(self):
        url = reverse("notes-list")
        self.client.force_login(self.participant)
        response = self.client.post(
            url,
            data={"proposal": self.prop.pk, "body": "Updated body"},
        )
        data = response.json()
        self.assertEqual(response.status_code, status.HTTP_200_OK, data)
        self.assertEqual(data["proposal"], self.prop.pk)
        self.assertEqual(data["body"], "Updated body")

    def test_create_with_messy_html(self):
        url = reverse("notes-list")
        self.client.force_login(self.participant)
        response = self.client.post(
            url,
            data={
                "proposal": self.prop2.pk,
                "body": '<p>I <b>dig</b> this!</p>\n     <p>Maybe a <a href="javascript:"">button</a>?</p><p>&nbsp;&nbsp;&nbsp;</p>\n<p> </p>',
            },
        )
        data = response.json()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, data)
        self.assertEqual(
            "<p>I <b>dig</b> this!</p>\n<p>Maybe a <a>button</a>?</p>", data["body"]
        )

    def test_update(self):
        url = reverse("notes-detail", kwargs={"pk": self.note.pk})
        self.client.force_login(self.participant)
        response = self.client.patch(
            url,
            data={"body": ""},
        )
        data = response.json()
        self.assertEqual(response.status_code, status.HTTP_200_OK, data)
        self.assertEqual("", data.get("body"))

    def test_update_other_users(self):
        url = reverse("notes-detail", kwargs={"pk": self.note.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(
            url,
            data={"body": ""},
        )
        data = response.json()
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, data)
        self.assertEqual({"detail": "No Note matches the given query."}, data)

    def test_delete(self):
        url = reverse("notes-detail", kwargs={"pk": self.note.pk})
        self.client.force_login(self.participant)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_list(self):
        url = reverse("notes-list")
        self.client.force_login(self.participant)
        response = self.client.get(url, data={"meeting": self.meeting.pk})
        data = response.json()
        self.assertEqual(response.status_code, status.HTTP_200_OK, data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0].get("pk"), self.note.pk)

    def test_list_no_filter(self):
        url = reverse("notes-list")
        self.client.force_login(self.participant)
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, data)
        self.assertEqual({"meeting": ["Required argument for action 'list'."]}, data)

    def test_delete_all(self):
        self.assertEqual(1, self.participant.notes.filter(meeting=self.meeting).count())
        url = reverse("notes-delete-all")
        self.client.force_login(self.participant)
        response = self.client.post(url, data={"meeting": self.meeting.pk})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(0, self.participant.notes.filter(meeting=self.meeting).count())
        self.assertEqual(
            1, self.participant.notes.filter(meeting=self.another_meeting).count()
        )
