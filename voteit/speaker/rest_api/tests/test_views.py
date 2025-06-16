from datetime import UTC
from datetime import datetime
from datetime import timedelta
import random

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.utils.timezone import now
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.agenda.models import AgendaItem
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.organisation.models import Organisation
from voteit.speaker.app.list_methods.priority import Priority
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.roles import ROLE_LIST_MODERATOR
from voteit.speaker.roles import ROLE_SPEAKER
from voteit.speaker.workflows import SpeakerSystemWf

User = get_user_model()


class SpeakerListsViewTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org: Organisation = Organisation.objects.get(pk=1)
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.ai = cls.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        cls.ai_private = cls.meeting.agenda_items.create(title="Private")
        cls.room = cls.meeting.rooms.create()
        cls.system = cls.meeting.speaker_systems.create(
            method_name="simple", room=cls.room
        )
        cls.slist = cls.system.speaker_lists.create()
        cls.list_moderator: User = User.objects.create_user("list_moderator")
        cls.participant: User = User.objects.get(username="participant")
        cls.moderator: User = User.objects.get(username="moderator")
        cls.speaker_user: User = cls.org.users.create(username="speaker_user")
        cls.system.add_roles(cls.speaker_user, ROLE_SPEAKER)
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.system.add_roles(cls.list_moderator, ROLE_LIST_MODERATOR)
        cls.part_speaker = cls.slist.speaker_items.create(user=cls.participant)
        cls.slist.reorder()

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
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            {"speaker_system": ['Invalid pk "-1" - object does not exist.']},
            response.json(),
        )

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

    def test_create_ai_from_another_meeting(self):
        new_meeting = Meeting.objects.create()
        new_ai = new_meeting.agenda_items.create()
        url = reverse("speaker-lists-list")
        data = {
            "title": "A think to talk about",
            "speaker_system": self.system.pk,
            "agenda_item": new_ai.pk,
        }
        self.client.force_login(self.list_moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            {
                "agenda_item": [
                    "SpeakerListSystem and AgendaItem belong to different meetings."
                ]
            },
            response.json(),
        )

    def test_list(self):
        url = reverse("speaker-lists-list")
        self.client.force_login(self.list_moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(0, len(response.json()))

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
        url = reverse("speaker-lists-detail", kwargs={"pk": self.slist.pk})
        self.client.force_login(self.list_moderator)
        response = self.client.delete(url)
        self.assertEqual(
            204,
            response.status_code,
        )
        self.assertRaises(ObjectDoesNotExist, self.slist.refresh_from_db)

    def test_delete_with_started_speaker(self):
        self.part_speaker.started = now()
        self.part_speaker.save()
        url = reverse("speaker-lists-detail", kwargs={"pk": self.slist.pk})
        self.client.force_login(self.list_moderator)
        response = self.client.delete(url)
        self.assertEqual(
            204,
            response.status_code,
        )
        self.assertRaises(ObjectDoesNotExist, self.slist.refresh_from_db)

    def test_get(self):
        url = reverse("speaker-lists-detail", kwargs={"pk": self.slist.pk})
        self.client.force_login(self.list_moderator)
        response = self.client.get(url)
        self.assertEqual(
            200,
            response.status_code,
        )
        self.assertEqual(
            {
                "pk": self.slist.pk,
                "title": "",
                "speaker_system": self.system.pk,
                "agenda_item": None,
                "state": "open",
                "queue": [self.participant.pk],
                "current": None,
                "room": self.room.pk,
                "meeting": self.meeting.pk,
            },
            response.json(),
        )

    def test_enter_moderator(self):
        url = reverse("speaker-lists-enter", args=[self.slist.pk])
        self.client.force_login(self.list_moderator)
        response = self.client.post(url)
        data = response.json()
        self.assertEqual(response.status_code, 201, data)
        data.pop("pk")
        self.assertEqual(
            {
                "seconds": None,
                "speaker_list": self.slist.pk,
                "started": None,
                "user": self.list_moderator.pk,
                "room": self.room.pk,
            },
            data,
        )

    def test_enter_speaker(self):
        url = reverse("speaker-lists-enter", args=[self.slist.pk])
        self.client.force_login(self.speaker_user)
        response = self.client.post(url)
        data = response.json()
        self.assertEqual(response.status_code, 201, data)
        data.pop("pk")
        self.assertEqual(
            {
                "seconds": None,
                "speaker_list": self.slist.pk,
                "started": None,
                "user": self.speaker_user.pk,
                "room": self.room.pk,
            },
            data,
        )

    def test_enter_speaker_already_in_list(self):
        url = reverse("speaker-lists-enter", args=[self.slist.pk])
        self.client.force_login(self.moderator)
        response = self.client.post(url)
        data = response.json()
        self.assertEqual(response.status_code, 201, data)
        created_pk = data.pop("pk")
        # Second call, user already in list
        response = self.client.post(url, data={"speaker_list": self.slist.pk})
        data = response.json()
        self.assertEqual(data["pk"], created_pk)
        self.assertEqual(response.status_code, 200, data)

        # Third call, user is speaking
        speaker = self.slist.speaker_items.get(
            user=self.moderator, started__isnull=True
        )
        speaker.start()
        speaker.save()
        response = self.client.post(url, data={"speaker_list": self.slist.pk})
        self.assertContains(
            response,
            f"You're missing the permission 'speaker.enter_speakerlist' on Speaker list {self.slist.pk}.",
            status_code=403,
        )

    def test_enter_participant_not_speaker(self):
        url = reverse("speaker-lists-enter", args=[self.slist.pk])
        self.client.force_login(self.participant)
        response = self.client.post(url)
        data = response.json()
        self.assertEqual(response.status_code, 403, data)
        self.assertEqual(
            {
                "detail": f"You're missing the permission 'speaker.enter_speakerlist' on Speaker list {self.slist.pk}."
            },
            data,
        )

    def test_leave(self):
        url = reverse("speaker-lists-leave", kwargs={"pk": self.slist.pk})
        self.client.force_login(self.participant)
        response = self.client.post(url)
        self.assertEqual(204, response.status_code)
        with self.assertRaises(ObjectDoesNotExist):
            self.part_speaker.refresh_from_db()
        response = self.client.post(url)
        self.assertEqual(404, response.status_code)

    def test_shuffle(self):
        url = reverse("speaker-lists-shuffle", kwargs={"pk": self.slist.pk})
        self.slist.speaker_items.create(user=self.moderator)
        self.slist.speaker_items.create(user=self.list_moderator)
        self.client.force_login(self.list_moderator)
        random.seed(100)
        response = self.client.post(url)
        random.seed()
        self.assertEqual(200, response.status_code)
        self.slist.refresh_from_db()
        self.assertEqual(
            [self.list_moderator.pk, self.moderator.pk, self.participant.pk],
            self.slist.order_list,
        )

    def test_shuffle_with_ongoing(self):
        self.slist.speaker_items.create(user=self.moderator, started=now())
        url = reverse("speaker-lists-shuffle", kwargs={"pk": self.slist.pk})
        self.client.force_login(self.list_moderator)
        response = self.client.post(url)
        self.assertEqual(403, response.status_code)
        self.assertEqual(
            {"detail": "Shuffle isn't allowed with an active speaker."}, response.json()
        )


class SpeakerListSystemViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.room = cls.meeting.rooms.create()
        cls.system = cls.meeting.speaker_systems.create(
            method_name="simple", state=SpeakerSystemWf.INACTIVE, room=cls.room
        )
        cls.slist = cls.system.speaker_lists.create()
        cls.participant: User = User.objects.create_user("participant")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.list_moderator: User = User.objects.create_user("list_moderator")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.system.add_roles(cls.list_moderator, ROLE_LIST_MODERATOR)
        # And the bad parts
        cls.other_meeting: Meeting = Meeting.objects.create(title="Other meeting")
        cls.other_room = cls.other_meeting.rooms.create()
        cls.other_system = cls.other_meeting.speaker_systems.create(
            method_name="simple", state=SpeakerSystemWf.INACTIVE, room=cls.other_room
        )
        cls.other_list = cls.other_system.speaker_lists.create()

    def test_create(self):
        room = self.meeting.rooms.create()
        url = reverse("speaker-list-systems-list")
        data = {"method_name": "simple", "room": room.pk}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            201,
        )
        data = response.json()
        self.assertIn("room", data)
        system = self.meeting.speaker_systems.get(pk=response.data.get("pk"))
        self.assertEqual(room.pk, data["room"])

    def test_create_bad_users(self):
        url = reverse("speaker-list-systems-list")
        room = self.meeting.rooms.create()
        data = {"room": room.pk, "method_name": "simple"}
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

    def test_create_room_ne(self):
        url = reverse("speaker-list-systems-list")
        data = {"method_name": "simple", "room": -1}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(
            {"room": ['Invalid pk "-1" - object does not exist.']}, response.json()
        )

    def test_create_with_missing_settings(self):
        room = self.meeting.rooms.create()
        url = reverse("speaker-list-systems-list")
        data = {"method_name": "priority", "room": room.pk, "settings": None}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual({"max_times": 0}, response.json().get("settings"))

    def test_list(self):
        url = reverse("speaker-list-systems-list")
        data = {"meeting": self.meeting.pk}
        self.client.force_login(self.moderator)
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(0, len(response.json()))

    def test_put(self):
        url = reverse("speaker-list-systems-detail", kwargs={"pk": self.system.pk})
        data = {
            "room": self.room.pk,
            "method_name": "simple",
            "safe_positions": 2,
        }
        self.client.force_login(self.moderator)
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, 200, response.json())
        self.system.refresh_from_db()
        self.assertEqual(2, self.system.safe_positions)

    def test_patch(self):
        url = reverse("speaker-list-systems-detail", kwargs={"pk": self.system.pk})
        data = {
            "very": "bogus",
            "meeting_roles_to_speaker": [str(ROLE_PARTICIPANT)],
        }
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(
            response.status_code,
            200,
        )
        self.system.refresh_from_db()
        self.assertEqual([ROLE_PARTICIPANT], self.system.meeting_roles_to_speaker)
        self.assertIsNone(self.system.settings)

    def test_patch_active_list(self):
        url = reverse("speaker-list-systems-detail", kwargs={"pk": self.system.pk})
        data = {
            "active_list": self.slist.pk,
        }
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        self.system.refresh_from_db()
        self.assertEqual(self.system.active_list, self.slist)
        response = self.client.patch(url, {"active_list": None})
        self.assertEqual(response.status_code, 200, response.json())
        self.system.refresh_from_db()
        self.assertIsNone(self.system.active_list)

    def test_patch_active_list_from_another_system(self):
        url = reverse("speaker-list-systems-detail", kwargs={"pk": self.system.pk})
        data = {
            "active_list": self.other_list.pk,
        }
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            {
                "active_list": [
                    f'Invalid pk "{self.other_list.pk}" - object does not exist.'
                ]
            },
            response.json(),
        )

    def test_patch_bad_roles(self):
        url = reverse("speaker-list-systems-detail", kwargs={"pk": self.system.pk})
        data = {"meeting_roles_to_speaker": ["Noo"]}
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(
            response.status_code,
            400,
        )
        self.assertIn("meeting_roles_to_speaker", response.json())

    def test_patch_with_settings_for_method_with(self):
        self.system.method_name = Priority.name
        self.system.save()
        url = reverse("speaker-list-systems-detail", kwargs={"pk": self.system.pk})
        data = {
            "settings": {
                "very": "bogus",
            },
        }
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(200, response.status_code)
        self.system.refresh_from_db()
        self.assertEqual({"max_times": 0}, self.system.settings.dict())

    def test_patch_with_odd_state(self):
        self.system.archive()
        self.system.save()
        url = reverse("speaker-list-systems-detail", kwargs={"pk": self.system.pk})
        data = {"show_time": True}
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(403, response.status_code)

    def test_method_name(self):
        url = reverse("speaker-list-systems-list")
        data = {
            "method_name": "404",
            "room": self.room.pk,
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertContains(response, "No list method_name 404", status_code=400)

    def test_settings_validation_error_update(self):
        self.system.method_name = Priority.name
        self.system.save()
        url = reverse("speaker-list-systems-detail", kwargs={"pk": self.system.pk})
        data = {
            "title": "Mkay",
            "settings": {
                "max_times": "bogus",
            },
        }
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(400, response.status_code)
        self.assertIn("settings", response.json())

    def test_settings_validation_error_create(self):
        room = self.meeting.rooms.create()
        url = reverse("speaker-list-systems-list")
        data = {
            "title": "Mkay",
            "method_name": Priority.name,
            "room": room.pk,
            "settings": {
                "max_times": "bogus",
            },
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(400, response.status_code)
        self.assertIn("settings", response.json())

    def test_delete(self):
        url = reverse("speaker-list-systems-detail", kwargs={"pk": self.system.pk})
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
        url = reverse("speaker-list-systems-detail", kwargs={"pk": self.system.pk})
        self.client.force_login(self.list_moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual({"max_times": 3}, data["settings"])

    def test_transition_moderator(self):
        url = reverse("speaker-list-systems-transitions", kwargs={"pk": self.system.pk})
        self.client.force_login(self.moderator)
        data = {"transition": "activate"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)

    def test_transition_list_moderator_not_allowed(self):
        url = reverse("speaker-list-systems-transitions", kwargs={"pk": self.system.pk})
        self.client.force_login(self.list_moderator)
        data = {"transition": "activate"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 403)


class HistoricSpeakerViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.room = cls.meeting.rooms.create()
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(
            state="ongoing", title="Ongoing"
        )
        cls.system: SpeakerListSystem = cls.meeting.speaker_systems.create(
            method_name="simple", room=cls.room
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
        cls.system.add_roles(cls.user_one, ROLE_SPEAKER)
        cls.system.add_roles(cls.list_moderator, ROLE_LIST_MODERATOR)
        cls.meeting.add_roles(cls.user_one, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.user_two_nospeaker, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
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
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            {"speaker_system": ["This field is required."]}, response.json()
        )
        response = self.client.get(url, data={"speaker_system": self.system.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(2, len(response.json()))
        # moderator
        self.client.force_login(self.moderator)
        response = self.client.get(url, data={"speaker_system": self.system.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(2, len(response.json()))
        # list moderator
        self.client.force_login(self.list_moderator)
        response = self.client.get(url, data={"speaker_system": self.system.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(2, len(response.json()))
        # outsider
        self.client.force_login(self.outsider)
        response = self.client.get(url, data={"speaker_system": self.system.pk})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            {
                "speaker_system": [
                    "Select a valid choice. That choice is not one of the available choices."
                ]
            },
            response.json(),
        )

    def test_history(self):
        url = reverse("speaker-history-list")
        self.client.force_login(self.user_one)
        response = self.client.get(url, data={"speaker_system": self.system.pk})
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


class SpeakerViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org: Organisation = Organisation.objects.get(pk=1)
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.room = cls.meeting.rooms.create()
        cls.system: SpeakerListSystem = cls.meeting.speaker_systems.create(
            method_name="simple", room=cls.room
        )
        cls.list_moderator: User = User.objects.create_user("list_moderator")
        cls.participant: User = User.objects.get(username="participant")
        cls.speaker_user: User = cls.org.users.create(username="speaker_user")
        cls.moderator: User = User.objects.get(username="moderator")
        cls.outsider: User = User.objects.create(username="outsider")
        cls.system.add_roles(cls.list_moderator, ROLE_LIST_MODERATOR)
        cls.system.add_roles(cls.speaker_user, ROLE_SPEAKER)
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
        cls.fifth_in_queue = cls.slist.speaker_items.create(user=cls.participant)
        cls.slist.reorder()

    def test_create(self):
        url = reverse("speakers-list")
        self.client.force_login(self.list_moderator)
        response = self.client.post(
            url, data={"speaker_list": self.slist.pk, "user": self.speaker_user.pk}
        )
        data = response.json()
        self.assertEqual(response.status_code, 201, data)
        data.pop("pk")
        self.assertEqual(
            {
                "seconds": None,
                "speaker_list": self.slist.pk,
                "started": None,
                "user": self.speaker_user.pk,
            },
            data,
        )

    def test_create_bad_user(self):
        url = reverse("speakers-list")
        self.client.force_login(self.list_moderator)
        response = self.client.post(
            url, data={"speaker_list": self.slist.pk, "user": self.outsider.pk}
        )
        data = response.json()
        self.assertEqual(response.status_code, 400, data)
        self.assertEqual({"user": ["User isn't a participant in this meeting."]}, data)

    def test_create_user_in_list(self):
        url = reverse("speakers-list")
        self.client.force_login(self.list_moderator)
        response = self.client.post(
            url, data={"speaker_list": self.slist.pk, "user": self.participant.pk}
        )
        data = response.json()
        self.assertEqual(response.status_code, 400, data)
        self.assertEqual({"user": ["User already in list."]}, data)

    def test_start(self):
        self.fourth_ongoing.stop()
        self.fourth_ongoing.save()
        self.system.active_list = self.slist
        self.system.save()
        url = reverse("speakers-start", kwargs={"pk": self.fifth_in_queue.pk})
        self.client.force_login(self.list_moderator)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        # And once again
        response = self.client.post(url)
        data = response.json()
        self.assertEqual(response.status_code, 404, data)

    def test_start_another_speaker_speaking(self):
        self.system.active_list = self.slist
        self.system.save()
        url = reverse("speakers-start", kwargs={"pk": self.fifth_in_queue.pk})
        self.client.force_login(self.list_moderator)
        response = self.client.post(url)
        data = response.json()
        self.assertEqual(response.status_code, 403, data)
        self.assertEqual(
            {
                "detail": f"You're missing the permission 'speaker.start_speaker' on Speaker id {self.fifth_in_queue.pk}."
            },
            data,
        )

    def test_stop(self):
        url = reverse("speakers-stop", kwargs={"pk": self.fourth_ongoing.pk})
        self.client.force_login(self.list_moderator)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.fourth_ongoing.refresh_from_db()
        self.assertIsNotNone(self.fourth_ongoing.seconds)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_undo(self):
        url = reverse("speakers-undo", kwargs={"pk": self.fourth_ongoing.pk})
        self.client.force_login(self.list_moderator)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.fourth_ongoing.refresh_from_db()
        self.assertIsNone(self.fourth_ongoing.started)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_list(self):
        # Not used right now
        url = reverse("speakers-list")
        self.client.force_login(self.list_moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Ongoing shouldn't show
        self.assertEqual(0, len(data))

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

    def test_patch_ongoing(self):
        url = reverse("speakers-detail", kwargs={"pk": self.fourth_ongoing.pk})
        data = {
            "seconds": "10",
        }
        self.client.force_login(self.list_moderator)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 404)

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
        self.assertEqual(response.status_code, 200)


class ExportSpeakersViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.outsider = User.objects.create(username="outsider")
        cls.meeting = Meeting.objects.get(pk=1)
        cls.room = cls.meeting.rooms.create()
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.int_user = cls.meeting.participants.create(
            userid="hao", first_name="Özgür", last_name="好", email="hello@world.se"
        )
        cls.sls = SpeakerListSystem.objects.create(
            method_name="simple", meeting=cls.meeting, room=cls.room
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
        self.client.force_login(self.outsider)
        url = reverse("export-speakers-json", kwargs={"pk": self.sls.pk})
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
