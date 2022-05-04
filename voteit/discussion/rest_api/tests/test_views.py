from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from rest_framework.test import APITestCase
from voteit.core.testing import mk_hashtag


User = get_user_model()


class DiscussionPostAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        from voteit.meeting.roles import (
            ROLE_MODERATOR,
            ROLE_PARTICIPANT,
            ROLE_DISCUSSER,
        )

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.ai = cls.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        cls.participant: User = User.objects.create_user("participant")
        cls.discusser: User = User.objects.create_user("discusser")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.discusser, ROLE_DISCUSSER)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.meeting_group = cls.meeting.groups.create()

    def test_create(self):
        url = reverse("discussion-posts-list")
        data = {
            "agenda_item": self.ai.pk,
            "body": "Hello " + mk_hashtag("world"),
        }
        for user, status in (
            (None, 401),
            (self.moderator, 201),
            (self.discusser, 201),
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
        url = reverse("discussion-posts-list")
        data = {
            "body": "bla",
            "agenda_item": -1,
        }
        self.client.force_login(self.discusser)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "No item found where pk==-1")

    def test_list(self):
        url = reverse("discussion-posts-list")
        self.client.force_login(self.discusser)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json())

    def test_put_author_discusser(self):
        disc = self.ai.discussions.create(body="hello", author=self.discusser)
        url = reverse("discussion-posts-detail", kwargs={"pk": disc.pk})
        data = {
            "body": "Sup?",
            "agenda_item": self.ai.pk,
        }
        self.client.force_login(self.discusser)
        response = self.client.put(url, data)
        self.assertEqual(
            response.status_code,
            403,
        )

    def test_patch_author_discusser(self):
        disc = self.ai.discussions.create(body="hello", author=self.discusser)
        url = reverse("discussion-posts-detail", kwargs={"pk": disc.pk})
        data = {
            "body": "Sup?",
        }
        self.client.force_login(self.discusser)
        response = self.client.patch(url, data)
        self.assertEqual(
            response.status_code,
            403,
        )

    def test_patch_author_discusser_moderator_user(self):
        disc = self.ai.discussions.create(body="hello", author=self.discusser)
        url = reverse("discussion-posts-detail", kwargs={"pk": disc.pk})
        data = {
            "body": "Sup?",
        }
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(
            response.status_code,
            200,
        )
        disc.refresh_from_db(fields=("body",))
        self.assertEqual("Sup?", disc.body)

    def test_delete(self):
        disc = self.ai.discussions.create(body="hello", author=self.discusser)
        url = reverse("discussion-posts-detail", kwargs={"pk": disc.pk})
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(
            response.status_code,
            204,
        )
        self.assertRaises(ObjectDoesNotExist, disc.refresh_from_db)

    def test_patch_author_normal_user(self):
        disc = self.ai.discussions.create(body="hello", author=self.discusser)
        url = reverse("discussion-posts-detail", kwargs={"pk": disc.pk})
        self.client.force_login(self.discusser)
        response = self.client.patch(url, data={"author": self.moderator.pk})
        self.assertEqual(
            response.status_code,
            403,
        )
        self.assertIn(
            "permission 'discussion.change_discussionpost'", response.json()["detail"]
        )

    def test_patch_author_moderator(self):
        disc = self.ai.discussions.create(body="hello", author=self.discusser)
        url = reverse("discussion-posts-detail", kwargs={"pk": disc.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data={"author": self.moderator.pk})
        self.assertEqual(
            response.status_code,
            200,
        )
        disc.refresh_from_db()
        self.assertEqual(disc.author, self.moderator)

    def test_patch_meeting_group_normal_user(self):
        disc = self.ai.discussions.create(body="hello", author=self.discusser)
        url = reverse("discussion-posts-detail", kwargs={"pk": disc.pk})
        self.client.force_login(self.discusser)
        response = self.client.patch(url, data={"meeting_group": self.meeting_group.pk})
        self.assertEqual(
            response.status_code,
            403,
        )
        self.assertIn(
            "permission 'discussion.change_discussionpost'", response.json()["detail"]
        )

    def test_patch_meeting_group_moderator(self):
        disc = self.ai.discussions.create(body="hello", author=self.discusser)
        url = reverse("discussion-posts-detail", kwargs={"pk": disc.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data={"meeting_group": self.meeting_group.pk})
        self.assertEqual(
            response.status_code,
            200,
        )
        disc.refresh_from_db()
        self.assertEqual(disc.meeting_group, self.meeting_group)
