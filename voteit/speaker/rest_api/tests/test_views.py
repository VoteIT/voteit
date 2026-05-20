from datetime import UTC
from datetime import datetime
from datetime import timedelta
from http import HTTPStatus
import random

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.utils.timezone import now
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.agenda.models import AgendaItem
from voteit.core.testing import run_permission_tests
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
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.ai = cls.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        cls.ai_private = cls.meeting.agenda_items.create(title="Private")
        cls.room = cls.meeting.rooms.create()
        cls.system = cls.meeting.speaker_systems.create(
            method_name="simple", room=cls.room
        )
        cls.slist = cls.system.speaker_lists.create()
        cls.list_moderator: User = cls.meeting.participants.create_user(
            "list_moderator"
        )
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
        data = {
            "title": "A think to talk about",
            "speaker_system": self.system.pk,
            "agenda_item": self.ai.pk,
        }
        for func, args in run_permission_tests(
            self,
            url=reverse("speaker-lists-list"),
            data=data,
            method="post",
            expected=[
                [None, 401],
                [self.moderator, 201],
                [self.participant, 403],
                [self.list_moderator, 201],
            ],
        ):
            func(*args)

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

    def test_transition_close(self):
        data = {"transition": "close"}
        slist = self.system.speaker_lists.create()
        for func, args in run_permission_tests(
            self,
            url=reverse("speaker-lists-transitions", kwargs={"pk": slist.pk}),
            data=data,
            method="post",
            expected=[
                [None, 401],
                [self.list_moderator, 201],
                [self.moderator, 201],
                [self.participant, 403],
            ],
        ):
            func(*args)

    def test_bad_transition_moderator(self):
        self.client.force_login(self.list_moderator)
        slist = self.system.speaker_lists.create()
        url = f"/api/speaker-lists/{slist.pk}/transitions/"
        data = {"transition": "woho"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    def test_patch(self):
        data = {"title": "Sup?"}
        slist = self.system.speaker_lists.create()
        for func, args in run_permission_tests(
            self,
            url=reverse("speaker-lists-detail", kwargs={"pk": slist.pk}),
            data=data,
            method="patch",
            expected=[
                [None, 401],
                [self.moderator, 200],
                [self.participant, 403],
                [self.list_moderator, 200],
            ],
        ):
            func(*args)

    def test_delete(self):
        for func, args in run_permission_tests(
            self,
            url=reverse("speaker-lists-detail", kwargs={"pk": self.slist.pk}),
            method="delete",
            expected=[
                [None, 401],
                [self.moderator, 204],
                [self.participant, 403],
                [self.list_moderator, 204],
            ],
        ):
            func(*args)

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
        for func, args in run_permission_tests(
            self,
            url=url,
            method="get",
            expected=[
                [None, 401],
                [self.participant, 200],
                [
                    self.list_moderator,
                    200,
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
                ],
                [self.speaker_user, 200],
            ],
        ):
            func(*args)

    def test_enter_permissions(self):
        url = reverse("speaker-lists-enter", args=[self.slist.pk])
        for func, args in run_permission_tests(
            self,
            url=url,
            method="post",
            expected=[
                [None, 401],
                [
                    self.participant,
                    403,
                    {
                        "detail": f"You're missing the permission 'speaker.enter_speakerlist' on Speaker list {self.slist.pk}."
                    },
                ],
                [self.list_moderator, 201],
                [self.speaker_user, 201],
            ],
        ):
            func(*args)

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
        self.slist.reorder()
        self.client.force_login(self.list_moderator)
        random.seed(5)
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
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.room = cls.meeting.rooms.create()
        cls.system = cls.meeting.speaker_systems.create(
            method_name="simple", state=SpeakerSystemWf.INACTIVE, room=cls.room
        )
        cls.slist = cls.system.speaker_lists.create()
        cls.participant: User = cls.meeting.participants.get(username="participant")
        cls.moderator: User = cls.meeting.participants.get(username="moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.list_moderator: User = cls.meeting.participants.create_user(
            "list_moderator"
        )
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
        data = response.json()
        self.assertEqual(response.status_code, 201, data)
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
        # And a second system
        cls.room2 = cls.meeting.rooms.create()
        cls.system2: SpeakerListSystem = cls.meeting.speaker_systems.create(
            method_name="simple", room=cls.room2
        )
        cls.slist2: SpeakerList = cls.system2.speaker_lists.create(agenda_item=cls.ai)
        cls.slist2.speaker_items.create(
            user=cls.user_one,
            seconds=5,
            started=now(),
        )

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
        response = self.client.get(reverse("speaker-history-list"))
        self.assertEqual(400, response.status_code)
        self.assertEqual({"meeting": ["This field is required."]}, response.json())
        response = self.client.get(
            url, data={"speaker_system": self.system.pk, "meeting": self.meeting.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(2, len(response.json()))
        # moderator
        self.client.force_login(self.moderator)
        response = self.client.get(
            url, data={"speaker_system": self.system.pk, "meeting": self.meeting.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(2, len(response.json()))
        # list moderator
        self.client.force_login(self.list_moderator)
        response = self.client.get(
            url, data={"speaker_system": self.system.pk, "meeting": self.meeting.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(2, len(response.json()))
        # outsider
        self.client.force_login(self.outsider)
        response = self.client.get(url, data={"meeting": self.meeting.pk})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            {
                "meeting": [
                    "Select a valid choice. That choice is not one of the available choices."
                ]
            },
            response.json(),
        )

    def test_history(self):
        url = reverse("speaker-history-list")
        self.client.force_login(self.user_one)
        response = self.client.get(
            url, data={"speaker_system": self.system.pk, "meeting": self.meeting.pk}
        )
        data = response.json()
        self.assertEqual(response.status_code, 200, data)
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

    def test_history_global_for_meeting(self):
        url = reverse("speaker-history-list")
        self.client.force_login(self.user_one)
        response = self.client.get(url, data={"meeting": self.meeting.pk})
        data = response.json()
        self.assertEqual(response.status_code, 200, data)
        self.assertEqual(
            sorted(
                [
                    {"user": self.user_one.pk, "times_spoken": 4, "seconds_spoken": 35},
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

    def test_patch_ongoing(self):
        url = reverse("speakers-detail", kwargs={"pk": self.fourth_ongoing.pk})
        data = {
            "seconds": "10",
        }
        self.client.force_login(self.list_moderator)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 404)

    def test_delete_ongoing(self):
        self.assertEqual(
            [self.moderator.pk, self.participant.pk], self.slist.order_list
        )
        url = reverse("speakers-detail", kwargs={"pk": self.fourth_ongoing.pk})
        self.client.force_login(self.list_moderator)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        with self.assertRaises(Speaker.DoesNotExist):
            self.fourth_ongoing.refresh_from_db()
        self.slist.refresh_from_db()
        self.assertEqual([self.participant.pk], self.slist.order_list)

    def test_delete_in_queue(self):
        self.assertEqual(
            [self.moderator.pk, self.participant.pk], self.slist.order_list
        )
        url = reverse("speakers-detail", kwargs={"pk": self.fifth_in_queue.pk})
        for func, args in run_permission_tests(
            self,
            url=url,
            method="delete",
            expected=[
                [self.moderator, 204],
                [self.list_moderator, 204],
                [self.speaker_user, 404],
                [self.participant, 404],
            ],
        ):
            func(*args)

    def test_get_not_finished(self):
        url = reverse("speakers-detail", kwargs={"pk": self.fourth_ongoing.pk})
        for func, args in run_permission_tests(
            self,
            url=url,
            method="get",
            expected=[
                [self.moderator, 200],
                [self.list_moderator, 200],
                [self.speaker_user, 404],
                [self.participant, 404],
            ],
        ):
            func(*args)

    def test_add_speaker(self):
        for func, args in run_permission_tests(
            self,
            url=reverse("speakers-list"),
            method="POST",
            data={"user": self.speaker_user.id, "speaker_list": self.slist.pk},
            expected=[
                [self.moderator, 201],
                [self.list_moderator, 201],
                [self.speaker_user, 403],
                [self.participant, 403],
            ],
        ):
            func(*args)

    def test_view_speaker(self):
        url = reverse("speakers-detail", kwargs={"pk": self.third.pk})
        for func, args in run_permission_tests(
            self,
            url=url,
            method="get",
            expected=[
                [self.moderator, 200],
                [self.list_moderator, 200],
                [self.speaker_user, 404],
                [self.participant, 404],
            ],
        ):
            func(*args)

    def test_change_speaker(self):
        url = reverse("speakers-detail", kwargs={"pk": self.third.pk})
        data = {
            "seconds": "10",
        }
        for func, args in run_permission_tests(
            self,
            url=url,
            method="patch",
            data=data,
            expected=[
                [self.moderator, 200],
                [self.list_moderator, 200],
                [self.speaker_user, 404],
                [self.participant, 404],
            ],
        ):
            func(*args)


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

    def test_export_permissions(self):
        url = reverse("export-speakers-json", kwargs={"pk": self.sls.pk})
        for func, args in run_permission_tests(
            self,
            url=url,
            method="get",
            expected=[
                [self.moderator, 200],
                [self.outsider, 404],
                [self.participant, 404],
            ],
        ):
            func(*args)

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
        self.assertEqual("", first_speaker.pop("agenda_item"))
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


class SpeakerSystemRolesListTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    list_url = reverse("speaker-system-roles-list")

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.room = cls.meeting.rooms.create()
        cls.system = cls.meeting.speaker_systems.create(
            method_name="simple", room=cls.room
        )
        cls.system.add_roles(cls.participant, ROLE_LIST_MODERATOR)

    def test_unauthorized(self):
        response = self.client.get(self.list_url, {"speaker_system": self.system.pk})
        self.assertEqual(HTTPStatus.UNAUTHORIZED, response.status_code)

    def test_participant_can_list(self):
        self.client.force_login(self.participant)
        response = self.client.get(self.list_url, {"speaker_system": self.system.pk})
        self.assertEqual(HTTPStatus.OK, response.status_code)
        self.assertEqual(1, len(response.json()))
        self.assertEqual(self.participant.pk, response.json()[0]["user"]["pk"])

    def test_no_system_returns_empty(self):
        self.client.force_login(self.participant)
        response = self.client.get(self.list_url)
        self.assertEqual(HTTPStatus.OK, response.status_code)
        self.assertEqual([], response.json())

    def test_user_id_in_filter(self):
        second = self.meeting.participants.get(username="moderator")
        self.system.add_roles(second, ROLE_LIST_MODERATOR)
        self.client.force_login(self.participant)
        response = self.client.get(
            self.list_url,
            {
                "speaker_system": self.system.pk,
                "user_id_in": f"{self.participant.pk},{second.pk}",
            },
        )
        self.assertEqual(HTTPStatus.OK, response.status_code)
        self.assertEqual(
            {self.participant.pk, second.pk},
            {item["user"]["pk"] for item in response.json()},
        )

    def test_user_id_in_filters_to_subset(self):
        self.client.force_login(self.participant)
        response = self.client.get(
            self.list_url,
            {
                "speaker_system": self.system.pk,
                "user_id_in": str(self.participant.pk),
            },
        )
        self.assertEqual(HTTPStatus.OK, response.status_code)
        self.assertEqual(1, len(response.json()))
        self.assertEqual(self.participant.pk, response.json()[0]["user"]["pk"])

    def test_other_meeting_participant_cannot_see(self):
        other_meeting = Meeting.objects.create()
        other_user = other_meeting.participants.create(username="outsider_slr")
        other_meeting.add_roles(other_user, ROLE_PARTICIPANT)
        self.client.force_login(other_user)
        response = self.client.get(self.list_url, {"speaker_system": self.system.pk})
        self.assertEqual(HTTPStatus.OK, response.status_code)
        self.assertEqual([], response.json())


class SpeakerSystemRolesChangeTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    add_url = reverse("speaker-system-roles-add-roles")
    remove_url = reverse("speaker-system-roles-remove-roles")

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.get(pk=1)
        cls.meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.room = cls.meeting.rooms.create()
        cls.system = cls.meeting.speaker_systems.create(
            method_name="simple", room=cls.room
        )

    def _add_payload(self, user=None, roles=None):
        return {
            "speaker_system": self.system.pk,
            "user": (user or self.participant).pk,
            "roles": [str(x) for x in (roles or [ROLE_LIST_MODERATOR])],
        }

    def test_add_unauthorized(self):
        response = self.client.post(self.add_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.UNAUTHORIZED, response.status_code)

    def test_add_participant_forbidden(self):
        self.client.force_login(self.participant)
        response = self.client.post(self.add_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.FORBIDDEN, response.status_code)

    def test_add_moderator(self):
        self.client.force_login(self.moderator)
        response = self.client.post(self.add_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.OK, response.status_code)
        self.assertIn(str(ROLE_LIST_MODERATOR), response.json()["assigned"])

    def test_add_logs_change(self):
        self.client.force_login(self.moderator)
        with self.assertLogs("voteit.event.roles") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(self.add_url, self._add_payload(), format="json")
                self.assertEqual(0, len(logs.records))
            self.assertEqual(1, len(logs.records))
        self.assertIn("Added", logs.records[0].getMessage())

    def test_add_bad_role(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.add_url, self._add_payload(roles=["jeff"]), format="json"
        )
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_add_user_from_other_org(self):
        other_org = Organisation.objects.create(title="Other org")
        other_user = other_org.users.create(username="spk_alien")
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.add_url, self._add_payload(user=other_user), format="json"
        )
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_remove_unauthorized(self):
        response = self.client.post(self.remove_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.UNAUTHORIZED, response.status_code)

    def test_remove_participant_forbidden(self):
        self.client.force_login(self.participant)
        response = self.client.post(self.remove_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.FORBIDDEN, response.status_code)

    def test_remove_moderator(self):
        self.system.add_roles(self.participant, ROLE_LIST_MODERATOR, ROLE_SPEAKER)
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.remove_url, self._add_payload(roles=[ROLE_SPEAKER]), format="json"
        )
        self.assertEqual(HTTPStatus.OK, response.status_code)
        self.assertNotIn(str(ROLE_SPEAKER), response.json()["assigned"])

    def test_remove_last_role_returns_no_content(self):
        self.system.add_roles(self.participant, ROLE_LIST_MODERATOR)
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.remove_url,
            self._add_payload(roles=[ROLE_LIST_MODERATOR]),
            format="json",
        )
        self.assertEqual(HTTPStatus.NO_CONTENT, response.status_code)

    def test_remove_logs_change(self):
        self.system.add_roles(self.participant, ROLE_LIST_MODERATOR, ROLE_SPEAKER)
        self.client.force_login(self.moderator)
        with self.assertLogs("voteit.event.roles") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(
                    self.remove_url,
                    self._add_payload(roles=[ROLE_SPEAKER]),
                    format="json",
                )
                self.assertEqual(0, len(logs.records))
            self.assertEqual(1, len(logs.records))
        self.assertIn("Removed", logs.records[0].getMessage())

    def test_remove_bad_role(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.remove_url, self._add_payload(roles=["jeff"]), format="json"
        )
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_remove_user_from_other_org(self):
        other_org = Organisation.objects.create(title="Other org")
        other_user = other_org.users.create(username="spk_alien2")
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.remove_url, self._add_payload(user=other_user), format="json"
        )
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)


class SpeakerSystemRolesAvailableRolesTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    url = reverse("speaker-system-roles-available")

    @classmethod
    def setUpTestData(cls):
        cls.participant = User.objects.get(username="participant")

    def test_anonymous_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(HTTPStatus.OK, response.status_code)

    def test_returns_all_roles(self):
        self.client.force_login(self.participant)
        response = self.client.get(self.url)
        names = {item["name"] for item in response.json()}
        self.assertEqual({str(ROLE_LIST_MODERATOR), str(ROLE_SPEAKER)}, names)

    def test_no_predicate_info_in_response(self):
        self.client.force_login(self.participant)
        response = self.client.get(self.url)
        for item in response.json():
            self.assertNotIn("predicate_info", item)

    def test_each_role_has_required_fields(self):
        self.client.force_login(self.participant)
        response = self.client.get(self.url)
        for item in response.json():
            self.assertIn("name", item)
            self.assertIn("title", item)
            self.assertIn("description", item)
            self.assertIn("require_names", item)
