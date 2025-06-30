from __future__ import annotations


from django.urls import reverse
from rest_framework.test import APITestCase

from voteit.core.workflows import EnabledWf
from voteit.meeting.models import Meeting
from voteit.organisation.models import Organisation
from voteit.participant_tags.components import GenderTags
from voteit.participant_tags.components import NamespacedTags
from voteit.participant_tags.components import PronounTags
from voteit.participant_tags.models import ParticipantTags


class ParticipantTagsViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org: Organisation = Organisation.objects.get(pk=1)
        cls.meeting = Meeting.objects.get(pk=1)
        cls.pronoun_component: NamespacedTags = cls.meeting.components.create(
            component_name=PronounTags.name,
            settings={"tags": ["han", "hon", "hen"], "many": True},
            state=EnabledWf.ON,
        )
        cls.gender_component: NamespacedTags = cls.meeting.components.create(
            component_name=GenderTags.name,
            settings={"tags": ["f", "m", "nb"]},
            state=EnabledWf.ON,
        )
        cls.participant = cls.org.users.get(username="participant")
        cls.participant_tags = cls.participant.meeting_tags.create(
            meeting=cls.meeting,
            tags={PronounTags.namespace: ["hon"], GenderTags.namespace: "f"},
        )

    def test_get(self):
        url = reverse("ptags-detail", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            {
                "pk": self.participant_tags.pk,
                "tags": {"gen": "f", "pron": ["hon"]},
                "meeting": self.meeting.pk,
                "user": self.participant.pk,
            },
            data,
        )

    def test_set_single(self):
        url = reverse("ptags-set", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.post(url, data={"tags": {GenderTags.namespace: "nb"}})
        data = response.json()
        self.assertEqual(response.status_code, 200, data)
        self.assertEqual(
            {
                "pk": self.participant_tags.pk,
                "tags": {
                    GenderTags.namespace: "nb",
                    PronounTags.namespace: ["hon"],
                },
                "meeting": self.meeting.pk,
                "user": self.participant.pk,
            },
            data,
        )

    def test_set_many(self):
        url = reverse("ptags-set", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.post(
            url, data={"tags": {PronounTags.namespace: ["hon", "hen"]}}
        )
        data = response.json()
        self.assertEqual(response.status_code, 200, data)
        self.assertEqual(
            {
                "pk": self.participant_tags.pk,
                "tags": {
                    GenderTags.namespace: "f",
                    PronounTags.namespace: ["hon", "hen"],
                },
                "meeting": self.meeting.pk,
                "user": self.participant.pk,
            },
            data,
        )

    def test_multiple_at_once(self):
        url = reverse("ptags-set", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.post(
            url,
            data={
                "tags": {
                    PronounTags.namespace: ["hon", "hen"],
                    GenderTags.namespace: "nb",
                }
            },
        )
        data = response.json()
        self.assertEqual(response.status_code, 200, data)
        self.assertEqual(
            {
                "pk": self.participant_tags.pk,
                "tags": {
                    GenderTags.namespace: "nb",
                    PronounTags.namespace: ["hon", "hen"],
                },
                "meeting": self.meeting.pk,
                "user": self.participant.pk,
            },
            data,
        )

    def test_bad_value_single(self):
        url = reverse("ptags-set", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.post(
            url,
            data={"tags": {GenderTags.namespace: "404"}},
        )
        data = response.json()
        self.assertEqual(response.status_code, 400, data)
        self.assertEqual(
            {"tags": [f"404 is not a valid tag for namespace {GenderTags.namespace}"]},
            data,
        )
        response = self.client.post(
            url,
            data={"tags": {GenderTags.namespace: ""}},
        )
        self.assertEqual(response.status_code, 400, data)
        response = self.client.post(
            url,
            data={"tags": {GenderTags.namespace: []}},
        )
        self.assertEqual(response.status_code, 400, data)
        response = self.client.post(
            url,
            data={"tags": {GenderTags.namespace: "!ö"}},
        )
        self.assertEqual(response.status_code, 400, data)

    def test_bad_value_many(self):
        url = reverse("ptags-set", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.post(
            url,
            data={"tags": {PronounTags.namespace: ["404"]}},
        )
        data = response.json()
        self.assertEqual(response.status_code, 400, data)
        self.assertEqual(
            {"tags": [f"404 is not a valid tag for namespace {PronounTags.namespace}"]},
            data,
        )
        response = self.client.post(
            url,
            data={"tags": {PronounTags.namespace: ""}},
        )
        self.assertEqual(response.status_code, 400, data)
        response = self.client.post(
            url,
            data={"tags": {PronounTags.namespace: []}},
        )
        self.assertEqual(response.status_code, 400, data)
        response = self.client.post(
            url,
            data={"tags": {PronounTags.namespace: ["!ö"]}},
        )
        self.assertEqual(response.status_code, 400, data)
        response = self.client.post(
            url,
            data={"tags": {"404": ["hello"]}},
        )
        self.assertEqual(response.status_code, 400, data)

    def test_remove_ns(self):
        url = reverse("ptags-remove-ns", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.post(
            url,
            data={"ns": [PronounTags.namespace, "404"]},
        )
        data = response.json()
        self.assertEqual(response.status_code, 200, data)
        self.assertEqual(
            {
                "pk": self.participant_tags.pk,
                "tags": {
                    GenderTags.namespace: "f",
                },
                "meeting": self.meeting.pk,
                "user": self.participant.pk,
            },
            data,
        )

    def test_remove_ns_full_delete(self):
        url = reverse("ptags-remove-ns", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.post(
            url,
            data={"ns": [PronounTags.namespace, "404", GenderTags.namespace]},
        )
        self.assertEqual(response.status_code, 204)
        with self.assertRaises(ParticipantTags.DoesNotExist):
            self.participant_tags.refresh_from_db()

    def test_delete(self):
        url = reverse("ptags-detail", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        with self.assertRaises(ParticipantTags.DoesNotExist):
            self.participant_tags.refresh_from_db()
