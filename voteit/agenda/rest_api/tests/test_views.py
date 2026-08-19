from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from voteit.messaging.testing import ChannelMessageCatcher
from voteit.messaging.testing import testing_channel_layers_setting
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase
from rest_framework.test import APITransactionTestCase

from voteit.agenda.messages import AgendaChanged
from voteit.agenda.models import AgendaItem
from voteit.agenda.rest_api.serializers import BulkAgendaItemSerializer
from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.core.testing import run_permission_tests
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.models import Meeting

User = get_user_model()


class AgendaItemViewTestCase(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.other_meeting: Meeting = Meeting.objects.create(
            title="Other meeting", state="ongoing"
        )
        cls.ai = cls.meeting.agenda_items.create(
            state="ongoing", title="Ongoing AI", tags=["hello", "world"]
        )
        cls.ai_private = cls.meeting.agenda_items.create(title="Private AI")
        cls.participant: User = cls.meeting.participants.get(username="participant")
        cls.moderator: User = cls.meeting.participants.get(username="moderator")
        cls.outsider: User = User.objects.create_user("outsider")

    def test_create(self):
        url = reverse("agendaitem-list")
        data = {
            "title": "Item no 1",
            "meeting": self.meeting.pk,
        }
        for func, args in run_permission_tests(
            self,
            url=url,
            data=data,
            method="post",
            expected=[
                [None, 401],
                [self.moderator, 201],
                [self.participant, 403],
            ],
        ):
            func(*args)

    def test_create_meeting_ne(self):
        url = reverse("agendaitem-list")
        data = {
            "title": "Stuff",
            "meeting": -1,
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        data = response.json()
        self.assertEqual(response.status_code, 400, data)
        self.assertEqual(
            {"meeting": ['Invalid pk "-1" - object does not exist.']}, data
        )

    def test_list(self):
        url = reverse("agendaitem-list")
        data = {
            "meeting": self.meeting.pk,
        }
        self.client.force_login(self.moderator)
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(2, len(response.json()))

    def test_list_participant(self):
        url = reverse("agendaitem-list")
        data = {
            "meeting": self.meeting.pk,
        }
        self.client.force_login(self.participant)
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json()))

    def test_list_other(self):
        url = reverse("agendaitem-list")
        data = {
            "meeting": self.meeting.pk,
        }
        for func, args in run_permission_tests(
            self,
            url=url,
            data=data,
            method="post",
            expected=[
                [None, 401],
                [self.outsider, 403],
            ],
        ):
            func(*args)

    def test_patch_change_meeting(self):
        url = reverse("agendaitem-detail", kwargs={"pk": self.ai.pk})
        data = {
            "meeting": self.other_meeting.pk,
        }
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(self.meeting.pk, data["meeting"])

    def test_patch_change_tags(self):
        url = reverse("agendaitem-detail", kwargs={"pk": self.ai.pk})
        data = {
            "tags": ["aa", "bb"],
        }
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(["aa", "bb"], data["tags"])

    def test_patch_remove_tags(self):
        url = reverse("agendaitem-detail", kwargs={"pk": self.ai.pk})
        data = {
            "tags": [],
        }
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([], data["tags"])

    def test_update_last_read_permissions(self):
        url = reverse("agendaitem-update-last-read", args=[self.ai.pk])
        for func, args in run_permission_tests(
            self,
            url=url,
            method="post",
            expected=[
                [None, 401],
                [self.moderator, 200],
                [self.participant, 200],
                [self.outsider, 404],
            ],
        ):
            func(*args)

    def test_update_last_read_creates_record(self):
        url = reverse("agendaitem-update-last-read", args=[self.ai.pk])
        self.client.force_login(self.participant)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(self.ai.pk, data["agenda_item"])
        self.assertIn("timestamp", data)
        self.assertTrue(self.ai.last_read_set.filter(user=self.participant).exists())


class ExportParticipantsViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")

    def test_permissions(self):
        url = reverse("export-agenda-items-json", kwargs={"pk": self.meeting.pk})
        for func, args in run_permission_tests(
            self,
            url=url,
            method="get",
            expected=[[None, 401], [self.participant, 404], [self.moderator, 200]],
        ):
            func(*args)

    def test_json(self):
        url = reverse("export-agenda-items-json", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(3, len(data))
        self.assertEqual(
            {
                "body": "could be tasty",
                "pk": 1,
                "state": "upcoming",
                "tags": "",
                "title": "Pickles",
            },
            data[0],
        )

    def test_csv(self):
        url = reverse("export-agenda-items-csv", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual("text/csv", response.headers.get("Content-Type"))
        rows = response.content.splitlines()
        self.assertIn(
            b"state,pk,title,body,tags",
            rows,
        )
        self.assertIn(
            b"upcoming,1,Pickles,could be tasty,",
            rows,
        )


class AgendaItemStateMachineSchemaTests(APITestCase):
    def test_detail(self):
        response = self.client.get("/api/state-machines/AgendaItemStateMachine/")
        self.assertEqual(200, response.status_code)
        self.assertIn("states", response.data)
        self.assertIn("events", response.data)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class AgendaItemBulkChangeViewTests(APITestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.participant: User = cls.meeting.participants.get(username="participant")
        cls.moderator: User = cls.meeting.participants.get(username="moderator")
        cls.outsider: User = User.objects.create_user("outsider")

    def _url(self):
        return reverse("agendaitem-bulk-change")

    def test_permissions(self):
        data = {
            "meeting": self.meeting.pk,
            "agenda_items": [1, 2],
            "block_proposals": True,
        }
        for func, args in run_permission_tests(
            self,
            url=self._url(),
            data=data,
            method="post",
            expected=[
                [None, 401],
                [self.moderator, 200],
                # meeting field rejects non-moderators
                [self.participant, 400],
                [self.outsider, 400],
            ],
        ):
            func(*args)

    def test_state_change_meeting_ongoing(self):
        self.meeting.state = "ongoing"
        self.meeting.save()
        self.client.force_login(self.moderator)
        with ChannelMessageCatcher(ModeratorsChannel, AgendaChanged) as messages:
            response = self.client.post(
                self._url(),
                {
                    "meeting": self.meeting.pk,
                    "agenda_items": [1, 2, 3],
                    "state": AgendaItemStateMachine.ongoing.value,
                },
                format="json",
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual({"changed": 3}, response.json())
        self.assertEqual(3, len(messages))
        for pk in (1, 2, 3):
            ai = AgendaItem.objects.get(pk=pk)
            self.assertEqual(AgendaItemStateMachine.ongoing.value, ai.state)

    def test_state_change_meeting_not_ongoing_is_noop(self):
        # meeting stays "upcoming" (fixture default) - make_ongoing requires
        # meeting_is_ongoing, so nothing should transition.
        self.client.force_login(self.moderator)
        with ChannelMessageCatcher(ModeratorsChannel, AgendaChanged) as messages:
            response = self.client.post(
                self._url(),
                {
                    "meeting": self.meeting.pk,
                    "agenda_items": [1, 3],
                    "state": AgendaItemStateMachine.ongoing.value,
                },
                format="json",
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual({"changed": 0}, response.json())
        self.assertEqual(0, len(messages))
        self.assertEqual(
            AgendaItemStateMachine.upcoming.value, AgendaItem.objects.get(pk=1).state
        )
        self.assertEqual(
            AgendaItemStateMachine.private.value, AgendaItem.objects.get(pk=3).state
        )

    def test_block_flags_skip_unchanged(self):
        ai_2 = AgendaItem.objects.get(pk=2)
        ai_2.block_proposals = True
        ai_2.block_discussion = True
        ai_2.save()
        self.client.force_login(self.moderator)
        with ChannelMessageCatcher(ModeratorsChannel, AgendaChanged) as messages:
            response = self.client.post(
                self._url(),
                {
                    "meeting": self.meeting.pk,
                    "agenda_items": [1, 2, 3],
                    "block_proposals": True,
                    "block_discussion": True,
                },
                format="json",
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual({"changed": 2}, response.json())
        self.assertEqual(2, len(messages))
        for pk in (1, 3):
            ai = AgendaItem.objects.get(pk=pk)
            self.assertTrue(ai.block_proposals)
            self.assertTrue(ai.block_discussion)

    def test_combined_change_no_duplicate_saves(self):
        self.meeting.state = "ongoing"
        self.meeting.save()
        self.client.force_login(self.moderator)
        with ChannelMessageCatcher(ModeratorsChannel, AgendaChanged) as messages:
            response = self.client.post(
                self._url(),
                {
                    "meeting": self.meeting.pk,
                    "agenda_items": [1, 2, 3],
                    "state": AgendaItemStateMachine.ongoing.value,
                    "block_proposals": True,
                    "block_discussion": True,
                },
                format="json",
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual({"changed": 3}, response.json())
        # Each item changed on two axes (state + block flags) but must only
        # be saved/notified once.
        self.assertEqual(3, len(messages))

    def test_state_change_blocked_by_ongoing_poll_mixed(self):
        self.meeting.state = "ongoing"
        self.meeting.save()
        ai1 = AgendaItem.objects.get(pk=1)
        ai1.state = AgendaItemStateMachine.ongoing.value
        ai1.save()
        ai1.polls.create(method_name="simple", state="ongoing")
        ai2 = AgendaItem.objects.get(pk=2)
        ai2.state = AgendaItemStateMachine.ongoing.value
        ai2.save()
        self.client.force_login(self.moderator)
        with ChannelMessageCatcher(ModeratorsChannel, AgendaChanged) as messages:
            response = self.client.post(
                self._url(),
                {
                    "meeting": self.meeting.pk,
                    "agenda_items": [1, 2],
                    "state": AgendaItemStateMachine.closed.value,
                },
                format="json",
            )
        self.assertEqual(200, response.status_code, response.content)
        self.assertEqual({"changed": 1}, response.json())
        self.assertEqual(1, len(messages))
        self.assertEqual(
            AgendaItemStateMachine.ongoing.value, AgendaItem.objects.get(pk=1).state
        )
        self.assertEqual(
            AgendaItemStateMachine.closed.value, AgendaItem.objects.get(pk=2).state
        )

    def test_requires_at_least_one_field(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self._url(),
            {"meeting": self.meeting.pk, "agenda_items": [1, 2]},
            format="json",
        )
        self.assertEqual(400, response.status_code)

    def test_duplicate_pks_rejected(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self._url(),
            {
                "meeting": self.meeting.pk,
                "agenda_items": [1, 1, 2],
                "block_proposals": True,
            },
            format="json",
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("agenda_items", response.json())

    def test_agenda_item_from_other_meeting_rejected(self):
        other_meeting = Meeting.objects.create(title="Other meeting")
        other_ai = other_meeting.agenda_items.create(title="Elsewhere")
        self.client.force_login(self.moderator)
        response = self.client.post(
            self._url(),
            {
                "meeting": self.meeting.pk,
                "agenda_items": [1, other_ai.pk],
                "block_proposals": True,
            },
            format="json",
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("agenda_items", response.json())


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class AgendaItemBulkChangeNoAmbientAtomicTests(APITransactionTestCase):
    """
    Uses APITransactionTestCase (no wrapping test-transaction) to check whether
    bulk_change's ai.sm.send() calls actually need an ambient atomic block, since
    close_and_deactivate_when_ai_closes (voteit.speaker.signals) is @ensure_atomic.
    """

    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    def _url(self):
        return reverse("agendaitem-bulk-change")

    def test_close_agenda_item_via_bulk_change(self):
        meeting = Meeting.objects.get(pk=1)
        meeting.state = "ongoing"
        meeting.save()
        moderator = meeting.participants.get(username="moderator")
        ai = AgendaItem.objects.get(pk=1)
        ai.state = AgendaItemStateMachine.ongoing.value
        ai.save()
        self.client.force_login(moderator)
        response = self.client.post(
            self._url(),
            {
                "meeting": meeting.pk,
                "agenda_items": [1],
                "state": AgendaItemStateMachine.closed.value,
            },
            format="json",
        )
        self.assertEqual(200, response.status_code, response.content)
        self.assertEqual({"changed": 1}, response.json())
        self.assertEqual(
            AgendaItemStateMachine.closed.value, AgendaItem.objects.get(pk=1).state
        )


class BulkAgendaItemSerializerQueryTests(APITestCase):
    """
    Fetching/validating the agenda items pks must be a single query,
    regardless of how many pks are requested (no N+1).
    """

    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.moderator: User = cls.meeting.participants.get(username="moderator")

    def _validate(self, pks):
        request = RequestFactory().post("/")
        request.user = self.moderator
        serializer = BulkAgendaItemSerializer(
            data={"meeting": self.meeting.pk, "agenda_items": pks},
            context={"request": request},
        )
        with CaptureQueriesContext(connection) as ctx:
            self.assertTrue(serializer.is_valid(), serializer.errors)
        return len(ctx.captured_queries)

    def test_query_count_independent_of_item_count(self):
        query_count_two = self._validate([1, 2])
        query_count_three = self._validate([1, 2, 3])
        self.assertEqual(query_count_two, query_count_three)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class AgendaItemBulkDeleteViewTests(APITestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.participant: User = cls.meeting.participants.get(username="participant")
        cls.moderator: User = cls.meeting.participants.get(username="moderator")
        cls.outsider: User = User.objects.create_user("outsider")

    def _url(self):
        return reverse("agendaitem-bulk-delete")

    def test_permissions(self):
        data = {"meeting": self.meeting.pk, "agenda_items": [1]}
        for func, args in run_permission_tests(
            self,
            url=self._url(),
            data=data,
            method="post",
            expected=[
                [None, 401],
                [self.participant, 400],
                [self.outsider, 400],
            ],
        ):
            func(*args)

    def test_delete(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self._url(),
            {"meeting": self.meeting.pk, "agenda_items": [1, 2, 3]},
            format="json",
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual({"deleted": 3}, response.json())
        self.assertFalse(self.meeting.agenda_items.filter(pk__in=[1, 2, 3]).exists())

    def test_delete_blocked_when_meeting_ongoing(self):
        self.meeting.state = "ongoing"
        self.meeting.save()
        self.client.force_login(self.moderator)
        response = self.client.post(
            self._url(),
            {"meeting": self.meeting.pk, "agenda_items": [1, 2, 3]},
            format="json",
        )
        self.assertEqual(400, response.status_code)
        self.assertTrue(self.meeting.agenda_items.filter(pk__in=[1, 2, 3]).exists())
