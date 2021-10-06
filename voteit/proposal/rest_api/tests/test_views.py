from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from rest_framework.test import APITestCase
from voteit.core.testing import mk_hashtag

User = get_user_model()


class ProposalsAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.agenda.models import AgendaItem
        from voteit.proposal.models import TextParagraph
        from voteit.proposal.models import TextDocument

        from voteit.meeting.roles import (
            ROLE_MODERATOR,
            ROLE_PARTICIPANT,
            ROLE_PROPOSER,
        )

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(
            state="ongoing", title="Ongoing"
        )
        cls.text_doc: TextDocument = cls.ai.text_documents.create(
            body="I am the eggman\nI am the walrus"
        )
        cls.para: TextParagraph = cls.text_doc.text_paragraphs.first()
        cls.participant: User = User.objects.create_user("participant")
        cls.proposer: User = User.objects.create_user("proposer")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.proposer, ROLE_PROPOSER)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)

    def test_create(self):
        url = reverse("proposal-list")
        data = {
            "agenda_item": self.ai.pk,
            "body": "Hello " + mk_hashtag("world"),
            "shortname": "proposal",
        }
        for user, status in (
            (None, 401),
            (self.moderator, 201),
            (self.proposer, 201),
            (self.participant, 403),
        ):
            if user:
                self.client.force_login(user)
            response = self.client.post(url, data)
            self.assertEqual(
                response.status_code,
                status,
                f"{user} action returned wrong response code",
            )

    def test_create_ai_ne(self):
        url = reverse("proposal-list")
        data = {"body": "bla", "agenda_item": -1, "shortname": "proposal"}
        self.client.force_login(self.proposer)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "No item found where pk==-1")

    def test_create_diff_proposal(self):
        url = reverse("proposal-list")
        data = {
            "agenda_item": self.ai.pk,
            "body": "Hello " + mk_hashtag("world"),
            "shortname": "diff_proposal",
            "paragraph": self.para.pk,
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(201, response.status_code)
        self.assertEqual(1, self.para.proposals.all().count())

    def test_create_diff_proposal_has_other_requirements(self):
        url = reverse("proposal-list")
        data = {
            "agenda_item": self.ai.pk,
            "body": "Hello " + mk_hashtag("world"),
            "shortname": "diff_proposal",
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(400, response.status_code)
        data = response.json()
        self.assertIn("paragraph", data)

    def test_create_diff_proposal_permissions(self):
        url = reverse("proposal-list")
        data = {
            "agenda_item": self.ai.pk,
            "body": "Hello " + mk_hashtag("world"),
            "shortname": "diff_proposal",
            "paragraph": self.para.pk,
        }
        for user, status in (
            (None, 401),
            (self.moderator, 201),
            (self.proposer, 201),
            (self.participant, 403),
        ):
            if user:
                self.client.force_login(user)
            response = self.client.post(url, data)
            self.assertEqual(
                response.status_code,
                status,
                f"{user} action returned wrong response code",
            )

    def test_list(self):
        url = reverse("proposal-list")
        self.client.force_login(self.proposer)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json())

    def test_put_author_proposer(self):
        prop = self.ai.proposals.create(body="hello", author=self.proposer)
        url = f"/api/proposals/{prop.pk}/"
        data = {
            "body": "Sup?",
            "agenda_item": self.ai.pk,
        }
        self.client.force_login(self.proposer)
        response = self.client.put(url, data)
        self.assertEqual(
            response.status_code,
            403,
        )

    def test_patch_author_proposer(self):
        prop = self.ai.proposals.create(body="hello", author=self.proposer)
        url = f"/api/proposals/{prop.pk}/"
        data = {
            "body": "Sup?",
        }
        self.client.force_login(self.proposer)
        response = self.client.patch(url, data)
        self.assertEqual(
            response.status_code,
            403,
        )

    def test_patch_author_proposer_moderator_user(self):
        prop = self.ai.proposals.create(body="hello", author=self.proposer)
        url = f"/api/proposals/{prop.pk}/"
        data = {
            "body": "Sup?",
        }
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(
            response.status_code,
            200,
        )
        prop.refresh_from_db(fields=("body",))
        self.assertEqual("Sup?", prop.body)

    def test_delete(self):
        prop = self.ai.proposals.create(body="hello", author=self.proposer)
        url = f"/api/proposals/{prop.pk}/"
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(
            response.status_code,
            204,
        )
        self.assertRaises(ObjectDoesNotExist, prop.refresh_from_db)


class TextDocumentAPITests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.agenda.models import AgendaItem
        from voteit.proposal.models import TextParagraph
        from voteit.proposal.models import TextDocument

        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.ai = cls.meeting.agenda_items.create(state="ongoing")
        User = get_user_model()
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.outsider = User.objects.create(username="outsider")
        cls.text_doc = cls.ai.text_documents.create(body="Hello")

    def test_create(self):
        url = reverse("text-document-list")
        data = {
            "agenda_item": self.ai.pk,
            "body": "Hello world",
            "base_tag": "hi",
        }
        for user, status in (
            (None, 401),
            (self.moderator, 201),
            (self.participant, 403),
            (self.outsider, 403),
        ):
            if user:
                self.client.force_login(user)
            response = self.client.post(url, data)
            self.assertEqual(
                response.status_code,
                status,
                f"{user} action returned wrong response code",
            )

    def test_create_ai_ne(self):
        url = reverse("text-document-list")
        data = {
            "body": "bla",
            "agenda_item": -1,
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "No item found where pk==-1")

    def test_list(self):
        url = reverse("text-document-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # We don't want to fetch items this way
        self.assertFalse(response.json())

    def test_delete(self):
        url = reverse("text-document-detail", kwargs={"pk": self.text_doc.pk})
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(
            response.status_code,
            204,
        )
        self.assertRaises(ObjectDoesNotExist, self.text_doc.refresh_from_db)
