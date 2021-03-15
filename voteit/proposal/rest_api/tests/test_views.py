from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.test import APITestCase
from voteit.core.testing import mk_hashtag


User = get_user_model()


class ProposalsAPITests(APITestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        from voteit.meeting.roles import (
            ROLE_MODERATOR,
            ROLE_PARTICIPANT,
            ROLE_PROPOSER,
        )

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        self.participant: User = User.objects.create_user("participant")
        self.proposer: User = User.objects.create_user("proposer")
        self.moderator: User = User.objects.create_user("moderator")
        self.outsider: User = User.objects.create_user("outsider")
        self.meeting.add_roles(self.participant, ROLE_PARTICIPANT)
        self.meeting.add_roles(self.proposer, ROLE_PROPOSER)
        self.meeting.add_roles(self.moderator, ROLE_MODERATOR)

    def test_create(self):
        url = f"/api/proposals/"
        data = {
            "agenda_item": self.ai.pk,
            "body": "Hello " + mk_hashtag("world"),
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
        url = f"/api/proposals/"
        data = {
            "body": "bla",
            "agenda_item": -1,
        }
        self.client.force_login(self.proposer)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "No item found where pk==-1")

    def test_list(self):
        url = f"/api/proposals/"
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
