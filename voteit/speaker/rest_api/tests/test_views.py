from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.utils.timezone import now
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
        url = reverse("speaker-lists-list")
        data = {
            "title": "A think to talk about",
            "speaker_system": self.system.pk,
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
        url = reverse("speaker-lists-list")
        data = {
            "title": "A think to talk about",
            "speaker_system": -1,
            "agenda_item": self.ai.pk,
        }
        self.client.force_login(self.list_moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "No item found where pk==-1")

    def test_create_ai_ne(self):
        url = reverse("speaker-lists-list")
        data = {
            "title": "A think to talk about",
            "speaker_system": self.system.pk,
            "agenda_item": -1,
        }
        self.client.force_login(self.list_moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
        # How do we get a sane exception here?
        # self.assertEqual(response.json().get("detail"), "No item found where pk==-1")

    def test_get(self):
        url = reverse("speaker-lists-list")
        data = {
            "speaker_system": self.system.pk,
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
        data = {
            "title": "Sup?",
            "speaker_system": self.system.pk,
            "meeting": self.meeting.pk,
            "agenda_item": self.ai.pk,
        }
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

    def test_retrieve(self):
        self.system.method_name = "priority"
        self.system.settings = {"max_times": 3}
        self.system.save()
        url = f"/api/speaker-list-systems/{self.system.pk}/"
        self.client.force_login(self.list_moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual({"max_times": 3}, data["settings"])

    def test_transition_list_moderator(self):
        url = f"/api/speaker-list-systems/{self.system.pk}/transitions/"
        self.client.force_login(self.list_moderator)
        data = {"transition": "activate"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)


class HistoricSpeakerViewTests(APITestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        self.system: SpeakerListSystem = self.meeting.speaker_systems.create(
            method_name="simple"
        )
        self.slist: SpeakerList = self.system.speaker_lists.create(agenda_item=self.ai)
        self.user_one: User = self.slist.speakers.create(username="one")
        self.user_two_nospeaker: User = self.slist.speakers.create(username="two")
        self.moderator: User = self.meeting.participants.create(username="moderator")
        self.list_moderator: User = self.meeting.participants.create(
            username="list_moderator"
        )
        self.participant: User = self.meeting.participants.create(
            username="participant"
        )
        self.outsider: User = User.objects.create(username="outsider")
        self.system.add_roles(self.user_one, "speaker")
        self.system.add_roles(self.list_moderator, "list_moderator")
        self.meeting.add_roles(self.user_one, "participant")
        self.meeting.add_roles(self.user_two_nospeaker, "participant")
        self.meeting.add_roles(self.moderator, "moderator")

    @property
    def _cut(self):
        from voteit.speaker.rest_api.serializers import HistoricSpeakerListSerializer

        return HistoricSpeakerListSerializer

    def test_list_perms(self):
        url = reverse("speaker-lists-history-list")
        # FIXME: We might want to fix the permissions here
        # anon
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)
        # Speaker/Participant
        self.client.force_login(self.user_one)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(0, len(response.json()))
        # moderator
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(0, len(response.json()))
        # list moderator
        self.client.force_login(self.list_moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(0, len(response.json()))
        # outsider
        self.client.force_login(self.outsider)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(0, len(response.json()))

    def test_get_perms(self):
        url = f"/api/speaker-lists-history/{self.slist.pk}/"
        # anon
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)
        # Speaker/Participant
        self.client.force_login(self.user_one)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # moderator
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # list moderator
        self.client.force_login(self.list_moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # outsider
        self.client.force_login(self.outsider)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_get_content(self):
        for i in range(1, 4):
            self.slist.speaker_items.create(
                user=self.user_one,
                seconds=i * 5,
                # Make sure there's a diff between started, since it's sorted on that
                started=now() - timedelta(seconds=10 - i),
            )
        self.slist.speaker_items.create(user=self.user_two_nospeaker, seconds=11)
        url = f"/api/speaker-lists-history/{self.slist.pk}/"
        self.client.force_login(self.user_one)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(self.slist.pk, data["pk"])
        self.assertEqual(2, len(data["previous"]))
        previous = data["previous"]
        first = [x for x in previous if x[0] == self.user_one.pk][0]
        second = [x for x in previous if x[0] == self.user_two_nospeaker.pk][0]
        self.assertEqual([self.user_one.pk, [5, 10, 15]], first)
        self.assertEqual([self.user_two_nospeaker.pk, [11]], second)
