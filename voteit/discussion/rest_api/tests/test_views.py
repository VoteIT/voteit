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
        from voteit.agenda.models import AgendaItem

        from voteit.meeting.roles import (
            ROLE_MODERATOR,
            ROLE_PARTICIPANT,
            ROLE_DISCUSSER,
        )

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(
            state="ongoing", title="Ongoing"
        )
        cls.post_one = cls.ai.discussions.create(body="One for open")
        cls.ai_private: AgendaItem = cls.meeting.agenda_items.create(title="Private")
        cls.post_two = cls.ai_private.discussions.create(body="Two for private")
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

    def test_list_with_ai(self):
        url = reverse("discussion-posts-list")
        self.client.force_login(self.discusser)
        response = self.client.get(url, {"agenda_item": self.ai.pk})
        self.assertEqual(response.status_code, 200)
        items = response.json()
        self.assertEqual(1, len(items))
        data = items[0]
        self.assertTrue(data.pop("created"))
        self.assertEqual(
            {
                "agenda_item": self.ai.pk,
                "pk": self.post_one.pk,
                "author": None,
                "body": "One for open",
                "meeting_group": None,
                "tags": [],
            },
            data,
        )

    def test_list_with_ai_outsider(self):
        url = reverse("discussion-posts-list")
        self.client.force_login(self.outsider)
        response = self.client.get(url, {"agenda_item": self.ai.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([], response.json())

    def test_list_with_private_ai(self):
        url = reverse("discussion-posts-list")
        self.client.force_login(self.discusser)
        response = self.client.get(url, {"agenda_item": self.ai_private.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([], response.json())

    def test_list_with_private_ai_moderator(self):
        url = reverse("discussion-posts-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url, {"agenda_item": self.ai_private.pk})
        self.assertEqual(response.status_code, 200)
        items = response.json()
        self.assertEqual(1, len(items))
        data = items[0]
        self.assertTrue(data.pop("created"))
        self.assertEqual(
            {
                "agenda_item": self.ai_private.pk,
                "pk": self.post_two.pk,
                "author": None,
                "body": "Two for private",
                "meeting_group": None,
                "tags": [],
            },
            data,
        )

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

    def test_create_meeting_group_not_in_meeting(self):
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        ai = meeting.agenda_items.create()
        disc = ai.discussions.create(body="I'm from another meeting")
        meeting.add_roles(self.moderator, "moderator")
        url = reverse("discussion-posts-detail", kwargs={"pk": disc.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data={"meeting_group": self.meeting_group.pk})
        self.assertEqual(
            response.status_code,
            400,
        )

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
