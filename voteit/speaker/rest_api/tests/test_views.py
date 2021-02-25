from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.speaker.roles import ROLE_LIST_MODERATOR

User = get_user_model()


class SpeakerListsViewTestCase(APITestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT
        from voteit.speaker.roles import ROLE_LIST_MODERATOR

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        self.ai_private = self.meeting.agenda_items.create(title="Private")
        self.system = self.meeting.speaker_systems.create(method_name="simple")
        self.list_moderator: User = User.objects.create_user("list_moderator")
        self.participant: User = User.objects.create_user("participant")
        self.moderator: User = User.objects.create_user("moderator")
        self.outsider: User = User.objects.create_user("outsider")
        self.meeting.add_roles(self.participant, ROLE_PARTICIPANT)
        self.meeting.add_roles(self.moderator, ROLE_MODERATOR)
        self.system.add_roles(self.list_moderator, ROLE_LIST_MODERATOR)

    def test_create(self):
        url = reverse("speakerlist-list")
        data = {
            "title": "A think to talk about",
            "list_system": self.system.pk,
            "agenda_item": self.ai.pk,
        }
        for user, status in (
            (None, 401),
            (self.moderator, 403),
            (self.participant, 403),
            (self.list_moderator, 201),
        ):
            if user:
                self.client.force_login(user)
            response = self.client.post(url, data)
            self.assertEqual(
                response.status_code,
                status,
                f"{user} action returned wrong response code",
            )

    def test_create_sls_ne(self):
        url = reverse("speakerlist-list")
        data = {
            "title": "A think to talk about",
            "list_system": -1,
            "agenda_item": self.ai.pk,
        }
        self.client.force_login(self.list_moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "No item found where pk==-1")

    def test_create_ai_ne(self):
        url = reverse("speakerlist-list")
        data = {
            "title": "A think to talk about",
            "list_system": self.system.pk,
            "agenda_item": -1,
        }
        self.client.force_login(self.list_moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
        # How do we get a sane exception here?
        # self.assertEqual(response.json().get("detail"), "No item found where pk==-1")

    def test_get(self):
        url = reverse("speakerlist-list")
        data = {
            "list_system": self.system.pk,
        }
        self.client.force_login(self.list_moderator)
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json())

    def test_transition_list_moderator(self):
        self.client.force_login(self.list_moderator)
        slist = self.system.speaker_lists.create()
        url = f"/api/speaker-lists/{slist.pk}/transitions/"
        data = {"transition": "close"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)

    def test_bad_transition_moderator(self):
        self.client.force_login(self.list_moderator)
        slist = self.system.speaker_lists.create()
        url = f"/api/speaker-lists/{slist.pk}/transitions/"
        data = {"transition": "woho"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    def test_transition_unauthorized_users(self):
        slist = self.system.speaker_lists.create()
        url = f"/api/speaker-lists/{slist.pk}/transitions/"
        data = {"transition": "close"}
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            401,
        )
        self.client.force_login(self.participant)
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            403,
        )

    def test_put(self):
        slist = self.system.speaker_lists.create()
        url = f"/api/speaker-lists/{slist.pk}/"
        data = {"title": "Sup?", "list_system": self.system.pk}
        self.client.force_login(self.list_moderator)
        response = self.client.put(url, data)
        self.assertEqual(
            response.status_code,
            200,
        )
        slist.refresh_from_db(fields=("title",))
        self.assertEqual("Sup?", slist.title)

    def test_patch(self):
        slist = self.system.speaker_lists.create()
        url = f"/api/speaker-lists/{slist.pk}/"
        data = {"title": "Sup?"}
        self.client.force_login(self.list_moderator)
        response = self.client.patch(url, data)
        self.assertEqual(
            response.status_code,
            200,
        )
        slist.refresh_from_db(fields=("title",))
        self.assertEqual("Sup?", slist.title)

    def test_delete(self):
        slist = self.system.speaker_lists.create()
        url = f"/api/speaker-lists/{slist.pk}/"
        self.client.force_login(self.list_moderator)
        response = self.client.delete(url)
        self.assertEqual(
            response.status_code,
            204,
        )
        self.assertRaises(ObjectDoesNotExist, slist.refresh_from_db)


class SpeakerListSystemViewTestCase(APITestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.system = self.meeting.speaker_systems.create(method_name="simple")
        self.participant: User = User.objects.create_user("participant")
        self.moderator: User = User.objects.create_user("moderator")
        self.outsider: User = User.objects.create_user("outsider")
        self.list_moderator: User = User.objects.create_user("list_moderator")
        self.meeting.add_roles(self.participant, ROLE_PARTICIPANT)
        self.meeting.add_roles(self.moderator, ROLE_MODERATOR)
        self.system.add_roles(self.list_moderator, ROLE_LIST_MODERATOR)

    def test_create(self):
        url = reverse("speakerlistsystem-list")
        data = {"meeting": self.meeting.pk, "method_name": "simple"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            201,
        )
        system = self.meeting.speaker_systems.get(pk=response.data.get("pk"))
        self.assertTrue(system.has_roles(self.moderator, ROLE_LIST_MODERATOR))

    def test_create_bad_users(self):
        url = reverse("speakerlistsystem-list")
        data = {"meeting": self.meeting.pk, "method_name": "simple"}
        for user, status in (
            (None, 401),
            (self.participant, 403),
            (self.list_moderator, 403),
        ):
            if user:
                self.client.force_login(user)
            response = self.client.post(url, data)
            self.assertEqual(
                response.status_code,
                status,
                f"{user} action returned wrong response code",
            )

    def test_create_meeting_ne(self):
        url = reverse("speakerlistsystem-list")
        data = {"meeting": -1, "method_name": "simple"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "No item found where pk==-1")

    def test_get(self):
        url = reverse("speakerlistsystem-list")
        data = {"meeting": self.meeting.pk, "method_name": "simple"}
        self.client.force_login(self.moderator)
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(0, len(response.json()))

    def test_put(self):
        url = f"/api/speaker-list-systems/{self.system.pk}/"
        data = {"meeting": self.meeting.pk, "title": "Mkay", "method_name": "simple"}
        self.client.force_login(self.list_moderator)
        response = self.client.put(url, data)
        self.assertEqual(
            response.status_code,
            200,
        )
        self.system.refresh_from_db(fields=("title",))
        self.assertEqual("Mkay", self.system.title)

    def test_patch(self):
        url = f"/api/speaker-list-systems/{self.system.pk}/"
        data = {"title": "Mkay"}
        self.client.force_login(self.list_moderator)
        response = self.client.patch(url, data)
        self.assertEqual(
            response.status_code,
            200,
        )
        self.system.refresh_from_db(fields=("title",))
        self.assertEqual("Mkay", self.system.title)

    def test_delete(self):
        url = f"/api/speaker-list-systems/{self.system.pk}/"
        self.client.force_login(self.list_moderator)
        response = self.client.delete(url)
        self.assertEqual(
            response.status_code,
            204,
        )
        self.assertRaises(ObjectDoesNotExist, self.system.refresh_from_db)
