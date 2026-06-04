from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from voteit.meeting.models import Meeting
from voteit.speaker.app.list_methods.simple import Simple


User = get_user_model()


class TransitionsMixinTests(APITestCase):
    """
    We'll test this view against the regular meeting endpoint
    """

    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.moderator = cls.meeting.participants.get(username="moderator")
        cls.participant = cls.meeting.participants.get(username="participant")
        cls.ai = cls.meeting.agenda_items.create()
        cls.room = cls.meeting.rooms.create()
        cls.sls = cls.meeting.speaker_systems.create(
            room=cls.room, method_name=Simple.name
        )
        cls.slist = cls.sls.speaker_lists.create(agenda_item=cls.ai)
        cls.speaker = cls.slist.speaker_items.create(user=cls.participant)

    @property
    def _cut(self):
        from voteit.core.rest_api.mixins import TransitionsMixin

        return TransitionsMixin

    @property
    def _url(self):
        return reverse("meeting-transitions", kwargs={"pk": self.meeting.pk})

    def test_available_upcoming(self):
        self.client.force_login(self.moderator)
        response = self.client.get(self._url)
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            [
                {
                    "name": "ongoing",
                    "permission": "meeting.moderate_meeting",
                    "source": "upcoming",
                    "target": "ongoing",
                    "title": "Make ongoing",
                    "has_perm": True,
                    "allowed": True,
                    "conditions": [
                        {
                            "allowed": True,
                            "title": "Must have valid electoral register policy name",
                            "name": "valid_er_policy_guard",
                        }
                    ],
                },
                {
                    "name": "request_delete",
                    "permission": "meeting.delete_meeting",
                    "source": "upcoming",
                    "target": "deleting",
                    "title": "Request delete...",
                    "conditions": [],
                    "has_perm": True,
                    "allowed": True,
                },
            ],
            response.json(),
        )

    def test_available_ongoing(self):
        self.meeting.ongoing()
        self.meeting.save()
        self.client.force_login(self.moderator)
        response = self.client.get(self._url)
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            [
                {
                    "name": "close",
                    "permission": "meeting.moderate_meeting",
                    "source": "ongoing",
                    "target": "closed",
                    "title": "Close",
                    "conditions": [
                        {
                            "allowed": True,
                            "title": "Meeting has ongoing polls - close them first",
                            "name": "no_ongoing_polls_guard",
                        }
                    ],
                    "has_perm": True,
                    "allowed": True,
                },
                {
                    "name": "request_delete",
                    "permission": "meeting.delete_meeting",
                    "source": "ongoing",
                    "target": "deleting",
                    "title": "Request delete...",
                    "conditions": [],
                    "has_perm": True,
                    "allowed": True,
                },
                {
                    "name": "upcoming",
                    "permission": "meeting.moderate_meeting",
                    "source": "ongoing",
                    "target": "upcoming",
                    "title": "Back to upcoming",
                    "conditions": [],
                    "has_perm": True,
                    "allowed": True,
                },
            ],
            response.json(),
        )

    def test_do_transition(self):
        self.client.force_login(self.moderator)
        response = self.client.post(self._url, data={"transition": "ongoing"})
        self.assertEqual(201, response.status_code)
        self.meeting.refresh_from_db()
        self.assertEqual("ongoing", self.meeting.state)

    def test_transition_to_same_state(self):
        self.client.force_login(self.moderator)
        response = self.client.post(self._url, data={"transition": "upcoming"})
        self.assertEqual(400, response.status_code)

    def test_transition_permission(self):
        url = reverse("meeting-transitions", kwargs={"pk": self.meeting.pk})
        self.client.force_login(self.participant)
        response = self.client.post(url, data={"transition": "ongoing"})
        self.assertEqual(403, response.status_code)

    def test_transition_guard(self):
        self.meeting.ongoing()
        self.meeting.save()
        self.ai.state = "ongoing"
        self.ai.save()
        self.ai.polls.create(state="ongoing", method_name="simple")
        url = reverse("agendaitem-event", kwargs={"pk": self.ai.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url, data={"event": "make_upcoming"})
        self.assertEqual(400, response.status_code)
        self.assertIn("transition", response.json())

    def test_transition_with_exception(self):
        self.meeting.ongoing()
        self.meeting.save()
        self.ai.state = "ongoing"
        self.ai.save()
        self.speaker.start()
        self.speaker.save()
        self.client.force_login(self.moderator)
        url = reverse("agendaitem-event", kwargs={"pk": self.ai.pk})
        response = self.client.post(url, data={"event": "close"})
        data = response.json()
        self.assertEqual(400, response.status_code, data)
        self.assertEqual({"transition": ["Finish active speaker first"]}, data)


class TransitionMixinAgendaTest(APITestCase):
    """
    Since transition is a mixin, we'll test it against agenda
    """

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.other_meeting: Meeting = Meeting.objects.create(
            title="Other meeting", state="ongoing"
        )
        cls.ai = cls.meeting.agenda_items.create(
            state="ongoing", title="Ongoing", tags=["hello", "world"]
        )
        cls.ai_private = cls.meeting.agenda_items.create(title="Private")
        cls.participant: User = User.objects.create_user("participant")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)

    def setUp(self):
        self.meeting.refresh_from_db()
        self.ai.refresh_from_db()

    def test_transition_moderator(self):
        url = reverse("agendaitem-event", kwargs={"pk": self.ai.pk})
        data = {"event": "make_upcoming"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

    def test_bad_transition_moderator(self):
        url = reverse("agendaitem-event", kwargs={"pk": self.ai.pk})
        data = {"event": "wooohoooo"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    def test_transition_unauthorized_users(self):
        url = reverse("agendaitem-event", kwargs={"pk": self.ai.pk})
        data = {"event": "make_upcoming"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 401)
        self.client.force_login(self.participant)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 403)

    def test_transition_conditions_not_met(self):
        self.meeting.state = "upcoming"
        self.meeting.save()
        url = reverse("agendaitem-event", kwargs={"pk": self.ai_private.pk})
        data = {"event": "make_ongoing"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
