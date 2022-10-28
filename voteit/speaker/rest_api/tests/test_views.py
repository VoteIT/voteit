from datetime import datetime
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.utils.timezone import now
from pytz import UTC
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.meeting.models import Meeting
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.roles import ROLE_LIST_MODERATOR
from voteit.speaker.workflows import SpeakerSystemWf

User = get_user_model()


class SpeakerListsViewTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT
        from voteit.speaker.roles import ROLE_LIST_MODERATOR

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.ai = cls.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        cls.ai_private = cls.meeting.agenda_items.create(title="Private")
        cls.system = cls.meeting.speaker_systems.create(method_name="simple")
        cls.list_moderator: User = User.objects.create_user("list_moderator")
        cls.participant: User = User.objects.create_user("participant")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.system.add_roles(cls.list_moderator, ROLE_LIST_MODERATOR)

    def test_create(self):
        url = reverse("speaker-lists-list")
        data = {
            "title": "A think to talk about",
            "speaker_system": self.system.pk,
            "agenda_item": self.ai.pk,
        }
        for user, status in (
            (None, 401),
            (self.moderator, 201),
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

    def test_list(self):
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
            204,
            response.status_code,
        )
        self.assertRaises(ObjectDoesNotExist, slist.refresh_from_db)


class SpeakerListSystemViewTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.system = cls.meeting.speaker_systems.create(
            method_name="simple", state=SpeakerSystemWf.INACTIVE
        )
        cls.participant: User = User.objects.create_user("participant")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.list_moderator: User = User.objects.create_user("list_moderator")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.system.add_roles(cls.list_moderator, ROLE_LIST_MODERATOR)

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

    def test_list(self):
        url = reverse("speakerlistsystem-list")
        data = {"meeting": self.meeting.pk}
        self.client.force_login(self.moderator)
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json()))

    def test_put(self):
        url = reverse("speakerlistsystem-detail", kwargs={"pk": self.system.pk})
        # url = f"/api/speaker-list-systems/{self.system.pk}/"
        data = {"meeting": self.meeting.pk, "title": "Mkay", "method_name": "simple"}
        self.client.force_login(self.moderator)
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
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(
            response.status_code,
            200,
        )
        self.system.refresh_from_db(fields=("title",))
        self.assertEqual("Mkay", self.system.title)

    def test_delete(self):
        url = f"/api/speaker-list-systems/{self.system.pk}/"
        self.client.force_login(self.moderator)
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

    def test_transition_moderator(self):
        url = f"/api/speaker-list-systems/{self.system.pk}/transitions/"
        self.client.force_login(self.moderator)
        data = {"transition": "activate"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)

    def test_transition_list_moderator_not_allowed(self):
        url = f"/api/speaker-list-systems/{self.system.pk}/transitions/"
        self.client.force_login(self.list_moderator)
        data = {"transition": "activate"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 403)


class HistoricSpeakerViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.agenda.models import AgendaItem
        from voteit.meeting.models import Meeting
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(
            state="ongoing", title="Ongoing"
        )
        cls.system: SpeakerListSystem = cls.meeting.speaker_systems.create(
            method_name="simple"
        )
        cls.slist: SpeakerList = cls.system.speaker_lists.create(agenda_item=cls.ai)
        cls.user_one: User = cls.slist.speakers.create(username="one")
        cls.user_two_nospeaker: User = cls.slist.speakers.create(username="two")
        cls.moderator: User = cls.meeting.participants.create(username="moderator")
        cls.list_moderator: User = cls.meeting.participants.create(
            username="list_moderator"
        )
        cls.participant: User = cls.meeting.participants.create(username="participant")
        cls.outsider: User = User.objects.create(username="outsider")
        cls.system.add_roles(cls.user_one, "speaker")
        cls.system.add_roles(cls.list_moderator, "list_moderator")
        cls.meeting.add_roles(cls.user_one, "participant")
        cls.meeting.add_roles(cls.user_two_nospeaker, "participant")
        cls.meeting.add_roles(cls.moderator, "moderator")
        # Add spoken time
        for i in range(1, 4):
            cls.slist.speaker_items.create(
                user=cls.user_one,
                seconds=i * 5,
                # Make sure there's a diff between started, since it's sorted on that
                started=now() - timedelta(seconds=10 - i),
            )
        cls.slist.speaker_items.create(user=cls.user_two_nospeaker, seconds=11)

    @property
    def _cut(self):
        from voteit.speaker.rest_api.serializers import HistoricSpeakerListSerializer

        return HistoricSpeakerListSerializer

    def test_list_perms(self):
        url = reverse("speaker-history-list") + f"?meeting={self.meeting.pk}"
        # anon
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)
        # Speaker/Participant
        self.client.force_login(self.user_one)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(2, len(response.json()))
        # moderator
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(2, len(response.json()))
        # list moderator
        self.client.force_login(self.list_moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(2, len(response.json()))
        # outsider
        self.client.force_login(self.outsider)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_without_meeting(self):
        url = reverse("speaker-history-list")
        self.client.force_login(self.user_one)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.json())

    def test_meeting_history(self):
        url = reverse("speaker-history-list") + f"?meeting={self.meeting.pk}"
        self.client.force_login(self.user_one)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            sorted(
                [
                    {"user": self.user_one.pk, "times_spoken": 3, "seconds_spoken": 30},
                    {
                        "user": self.user_two_nospeaker.pk,
                        "times_spoken": 1,
                        "seconds_spoken": 11,
                    },
                ],
                key=lambda x: x["user"],
            ),
            sorted(data, key=lambda x: x["user"]),
        )


class SpeakerViewSetTestCase(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.system: SpeakerListSystem = cls.meeting.speaker_systems.create(
            method_name="simple"
        )
        cls.list_moderator: User = User.objects.create_user("list_moderator")
        cls.participant: User = User.objects.get(username="participant")
        cls.moderator: User = User.objects.get(username="moderator")
        cls.outsider: User = User.objects.create(username="outsider")
        cls.system.add_roles(cls.list_moderator, ROLE_LIST_MODERATOR)
        cls.slist: SpeakerList = cls.system.speaker_lists.create()
        # And some precious entries
        cls.first = cls.slist.speaker_items.create(
            user=cls.participant, started=datetime(1911, 1, 1, tzinfo=UTC), seconds=1
        )
        cls.second = cls.slist.speaker_items.create(
            user=cls.moderator, started=datetime(1912, 1, 1, tzinfo=UTC), seconds=2
        )
        cls.third = cls.slist.speaker_items.create(
            user=cls.participant, started=datetime(1913, 1, 1, tzinfo=UTC), seconds=3
        )
        cls.fourth_ongoing = cls.slist.speaker_items.create(
            user=cls.moderator, started=datetime(1914, 1, 1, tzinfo=UTC)
        )

    def test_create(self):
        url = reverse("speakers-list")
        data = {
            "speaker_list": self.slist.pk,
        }
        self.client.force_login(self.list_moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 405)

    def test_list(self):
        url = reverse("speakers-list")
        data = {
            "speaker_list": self.slist.pk,
        }
        self.client.force_login(self.list_moderator)
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Ongoing shouldn't show
        self.assertEqual(3, len(data))

    def test_put(self):
        url = reverse("speakers-detail", kwargs={"pk": self.third.pk})
        data = {
            "seconds": "10",
        }
        self.client.force_login(self.list_moderator)
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, 200)
        self.third.refresh_from_db()
        self.assertEqual(10, self.third.seconds)

    def test_patch(self):
        url = reverse("speakers-detail", kwargs={"pk": self.third.pk})
        data = {
            "seconds": "10",
        }
        self.client.force_login(self.list_moderator)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        self.third.refresh_from_db()
        self.assertEqual(10, self.third.seconds)

    def test_delete(self):
        url = reverse("speakers-detail", kwargs={"pk": self.third.pk})
        self.client.force_login(self.list_moderator)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        with self.assertRaises(Speaker.DoesNotExist):
            self.third.refresh_from_db()

    def test_get_outsider(self):
        url = reverse("speakers-detail", kwargs={"pk": self.third.pk})
        self.client.force_login(self.outsider)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_get(self):
        url = reverse("speakers-detail", kwargs={"pk": self.third.pk})
        self.client.force_login(self.list_moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(self.third.pk, data["pk"])

    def test_get_not_finished(self):
        url = reverse("speakers-detail", kwargs={"pk": self.fourth_ongoing.pk})
        self.client.force_login(self.list_moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class ExportParticipantsViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.int_user = cls.meeting.participants.create(
            userid="hao", first_name="Özgür", last_name="好", email="hello@world.se"
        )
        cls.sls = SpeakerListSystem.objects.create(
            method_name="simple", meeting=cls.meeting
        )
        cls.list_one = cls.sls.speaker_lists.create()
        cls.list_one.speaker_items.create(
            user=cls.int_user, seconds=12, created=now(), started=now()
        )
        cls.list_one.speaker_items.create(
            user=cls.moderator, seconds=14, created=now(), started=now()
        )
        cls.list_one.speaker_items.create(
            user=cls.participant, seconds=33, created=now(), started=now()
        )

    def test_not_allowed(self):
        url = reverse("export-speakers-json", kwargs={"pk": self.sls.pk})
        self.client.force_login(self.participant)
        response = self.client.get(url)
        self.assertContains(
            response, "permission speaker.manage_speakerlistsystem", status_code=403
        )

    def test_csv_no_data(self):
        self.sls.speaker_lists.all().delete()
        self.client.force_login(self.moderator)
        url = reverse("export-speakers-csv", kwargs={"pk": self.sls.pk})
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

    def test_json(self):
        url = reverse("export-speakers-json", kwargs={"pk": self.sls.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(3, len(data))
        first_speaker = data[0]
        self.assertIsNotNone(first_speaker.pop("started"))
        self.assertIsNotNone(first_speaker.pop("created"))
        self.assertIsNotNone(self.list_one.pk, first_speaker.pop("speaker_list"))
        self.assertEqual("Özgür", first_speaker.pop("first_name"))
        self.assertEqual("好", first_speaker.pop("last_name"))
        self.assertEqual("hello@world.se", first_speaker.pop("email"))
        self.assertEqual("hao", first_speaker.pop("userid"))
        self.assertEqual(12, first_speaker.pop("seconds"))
        self.assertFalse(first_speaker.keys())

    def test_csv(self):
        url = reverse("export-speakers-csv", kwargs={"pk": self.sls.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual("text/csv", response.headers.get("Content-Type"))
        rows = response.content.splitlines()
        oz_row = rows[1]
        self.assertIn(b"hello@world.se", oz_row)
        self.assertIn(b"\xe5\xa5\xbd", oz_row)
