from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.poll.app.polls.simple import Simple as SimplePoll
from voteit.room.messages import RoomChanged
from voteit.speaker.app.list_methods.simple import Simple
from voteit.speaker.models import Speaker
from voteit.speaker.roles import ROLE_LIST_MODERATOR

User = get_user_model()


class RoomsViewTestCase(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.ai = cls.meeting.agenda_items.create()
        cls.other_meeting: Meeting = Meeting.objects.create()
        # Props
        cls.prop1 = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.prop3 = cls.ai.proposals.create()
        # Users
        cls.participant: User = User.objects.get(username="participant")
        cls.moderator: User = User.objects.get(username="moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        # Default room
        cls.room = cls.meeting.rooms.create(title="Room", handler=cls.moderator)
        cls.room.highlighted_proposals.create(proposal=cls.prop1)
        cls.room.highlighted_proposals.create(proposal=cls.prop2)
        # Speaker system
        cls.sls = cls.meeting.speaker_systems.create(
            method_name=Simple.name, room=cls.room
        )

    def test_create(self):
        url = reverse("rooms-list")
        data = {
            "title": "A big room",
            "meeting": self.meeting.pk,
        }
        for user, status in (
            (None, 401),
            (self.moderator, 201),
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
        url = reverse("rooms-list")
        data = {
            "meeting": self.meeting.pk,
        }
        self.client.force_login(self.participant)
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json()))

    def test_list_anon(self):
        url = reverse("rooms-list")
        data = {
            "meeting": self.meeting.pk,
        }
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 401)

    def test_list_outsider(self):
        url = reverse("rooms-list")
        self.client.force_login(self.outsider)
        data = {
            "meeting": self.meeting.pk,
        }
        response = self.client.get(url, data)
        data = response.json()
        self.assertEqual(response.status_code, 400, data)
        self.assertDictEqual(
            {
                "meeting": [
                    "Select a valid choice. That choice is not one of the available choices."
                ]
            },
            data,
        )

    def test_list_force_meeting(self):
        url = reverse("rooms-list")
        self.client.force_login(self.participant)
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(response.status_code, 400, data)
        self.assertDictEqual(
            {"meeting": ["Required argument for action 'list'."]}, data
        )

    def test_patch_change_meeting(self):
        url = reverse("rooms-detail", kwargs={"pk": self.room.pk})
        data = {"meeting": self.other_meeting.pk}
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(self.meeting.pk, data["meeting"])

    def test_handle_as_speaker_manager(self):
        url = reverse("rooms-handle-speaker", kwargs={"pk": self.room.pk})
        speaker_manager = User.objects.create_user("speaker_manager")
        self.client.force_login(speaker_manager)
        data = {"body": "How about that?", "title": "Not changed"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 404)
        self.meeting.add_roles(speaker_manager, ROLE_PARTICIPANT)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 403)
        self.sls.add_roles(speaker_manager, ROLE_LIST_MODERATOR)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        self.room.refresh_from_db()
        self.assertEqual("Room", self.room.title)  # Not changed
        self.assertEqual("How about that?", self.room.body)

    def test_patch_change_as_regular_user(self):
        url = reverse("rooms-detail", kwargs={"pk": self.room.pk})
        data = {"body": "body"}
        self.client.force_login(self.participant)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 403)
        self.sls.delete()
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 403)

    def test_patch_change_highlighted(self):
        url = reverse("rooms-handle", kwargs={"pk": self.room.pk})
        self.client.force_login(self.moderator)
        data = {"highlighted": [self.prop3.pk, self.prop2.pk]}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [self.prop3.pk, self.prop2.pk], list(self.room.highlighted_proposal_pks)
        )

    def test_patch_change_highlighted_no_handler(self):
        self.room.handler = None
        self.room.save()
        url = reverse("rooms-handle", kwargs={"pk": self.room.pk})
        self.client.force_login(self.moderator)
        data = {"highlighted": [self.prop3.pk, self.prop2.pk]}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        self.room.refresh_from_db()
        self.assertEqual(self.moderator, self.room.handler)

    def test_patch_change_highlighted_other_handler(self):
        self.room.handler = self.participant
        self.room.save()
        url = reverse("rooms-handle", kwargs={"pk": self.room.pk})
        self.client.force_login(self.moderator)
        data = {"highlighted": [self.prop3.pk, self.prop2.pk]}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        self.room.refresh_from_db()
        self.assertEqual(self.moderator, self.room.handler)

    def test_patch_change_highlighted_order(self):
        url = reverse("rooms-handle", kwargs={"pk": self.room.pk})
        self.client.force_login(self.moderator)
        data = {"highlighted": [self.prop1.pk, self.prop2.pk]}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [self.prop1.pk, self.prop2.pk], list(self.room.highlighted_proposal_pks)
        )

    def test_patch_blank_highlighted(self):
        url = reverse("rooms-handle", kwargs={"pk": self.room.pk})
        self.client.force_login(self.moderator)
        data = {"highlighted": []}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([], list(self.room.highlighted_proposal_pks))

    def test_patch_set_ai_and_poll(self):
        url = reverse("rooms-handle", kwargs={"pk": self.room.pk})
        self.client.force_login(self.moderator)
        data = {"agenda_item": self.ai.pk, "poll": None}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(None, data["poll"])
        self.assertEqual(self.ai.pk, data["agenda_item"])

    def test_patch_set_poll_resets_show_ballot(self):
        poll = self.meeting.polls.create(method_name=SimplePoll.name)
        self.room.show_ballot = True
        self.room.save()
        url = reverse("rooms-handle", kwargs={"pk": self.room.pk})
        self.client.force_login(self.moderator)
        data = {"poll": poll.pk}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        self.room.refresh_from_db()
        self.assertFalse(self.room.show_ballot)

    @patch.object(MeetingChannel, "sync_publish")
    def test_patch_with_token_includes_token_in_message(self, mock_publish):
        url = reverse("rooms-handle", kwargs={"pk": self.room.pk})
        self.client.force_login(self.moderator)
        data = {"highlight": [self.prop1.pk, self.prop2.pk], "token": "abc"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_publish.called)
        messages = [
            x.args[0]
            for x in mock_publish.mock_calls
            if isinstance(x.args[0], RoomChanged)
        ]
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertEqual(self.room.pk, msg.data.pk)
        self.assertEqual("abc", msg.data.token)

    def test_room_status(self):
        """Delete preflight check"""
        slist = self.sls.speaker_lists.create()
        slist.speaker_items.create(user=self.moderator)
        slist.speaker_items.create(user=self.participant)
        self.client.force_login(self.moderator)
        url = reverse("rooms-status", kwargs={"pk": self.room.pk})
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(data["speaker_lists"], 1)
        self.assertEqual(data["speakers"], 2)

    def test_delete_with_sls_and_speaker(self):
        slist = self.sls.speaker_lists.create()
        speaker = slist.speaker_items.create(user=self.moderator)
        self.client.force_login(self.moderator)
        url = reverse("rooms-detail", kwargs={"pk": self.room.pk})
        response = self.client.delete(url)
        self.assertEqual(204, response.status_code)
        with self.assertRaises(Speaker.DoesNotExist):
            speaker.refresh_from_db()

    def test_delete_without_sls(self):
        self.client.force_login(self.moderator)
        self.sls.delete()
        url = reverse("rooms-detail", kwargs={"pk": self.room.pk})
        response = self.client.delete(url)
        self.assertEqual(204, response.status_code)
