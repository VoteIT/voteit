from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.speaker.app.list_methods.simple import Simple
from voteit.speaker.roles import ROLE_LIST_MODERATOR
from voteit.poll.app.polls.simple import Simple as SimplePoll

User = get_user_model()


class RoomsViewTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.ai = cls.meeting.agenda_items.create()
        cls.other_meeting: Meeting = Meeting.objects.create()
        # Props
        cls.prop1 = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.prop3 = cls.ai.proposals.create()
        # Users
        cls.participant: User = User.objects.create_user("participant")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        # Default room
        cls.room = cls.meeting.rooms.create(title="Room", handler=cls.moderator)
        cls.room.highlighted_proposals.create(proposal=cls.prop1)
        cls.room.highlighted_proposals.create(proposal=cls.prop2)
        # Speaker system
        cls.sls = cls.meeting.speaker_systems.create(
            method_name="simple", room=cls.room
        )

    def setUp(self):
        self.meeting.refresh_from_db()

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
        self.assertEqual(response.status_code, 200)
        self.assertEqual([], response.json())

    def test_patch_change_meeting(self):
        url = reverse("rooms-detail", kwargs={"pk": self.room.pk})
        data = {"meeting": self.other_meeting.pk}
        self.client.force_login(self.moderator)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(self.meeting.pk, data["meeting"])

    def test_patch_change_as_speaker_manager(self):
        url = reverse("rooms-detail", kwargs={"pk": self.room.pk})
        speaker_manager = User.objects.create_user("speaker_manager")
        self.client.force_login(speaker_manager)
        data = {"body": "How about that?", "title": "Not changed"}
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
        data = response.json()
        self.assertEqual([self.prop3.pk, self.prop2.pk], data["highlighted"])
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
        self.assertContains(
            response,
            "You're missing the permission 'room.handle_room'",
            status_code=403,
        )

    def test_patch_change_highlighted_other_handler(self):
        self.room.handler = self.participant
        self.room.save()
        url = reverse("rooms-handle", kwargs={"pk": self.room.pk})
        self.client.force_login(self.moderator)
        data = {"highlighted": [self.prop3.pk, self.prop2.pk]}
        response = self.client.patch(url, data)
        self.assertContains(
            response,
            "You're missing the permission 'room.handle_room'",
            status_code=403,
        )

    def test_patch_change_highlighted_order(self):
        url = reverse("rooms-handle", kwargs={"pk": self.room.pk})
        self.client.force_login(self.moderator)
        data = {"highlighted": [self.prop1.pk, self.prop2.pk]}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([self.prop1.pk, self.prop2.pk], data["highlighted"])
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
        self.assertEqual([], data["highlighted"])
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

    def test_patch_moderator_replaces_handler(self):
        self.room.handler = self.participant
        self.room.save()
        url = reverse("rooms-set-handler", kwargs={"pk": self.room.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.room.refresh_from_db()
        self.assertEqual(self.moderator, self.room.handler)
