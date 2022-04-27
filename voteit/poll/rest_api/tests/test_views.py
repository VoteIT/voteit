from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase


User = get_user_model()


class PollViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting",
        )
        cls.ai = cls.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        cls.ai_private = cls.meeting.agenda_items.create(title="Private")
        cls.prop = cls.ai.proposals.create()
        cls.participant: User = User.objects.create_user("participant")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)

    def test_create(self):
        url = reverse("poll-list")
        data = {
            "title": "Let's vote",
            "meeting": self.meeting.pk,
            "method_name": "simple",
            "agenda_item": self.ai.pk,
            "proposals": [self.prop.pk],
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)

    def test_create_wrong_user(self):
        url = reverse("poll-list")
        data = {
            "title": "Let's vote",
            "meeting": self.meeting.pk,
            "method_name": "simple",
            "agenda_item": self.ai.pk,
            "proposals": [self.prop.pk],
        }
        for user, status in (
            (None, 401),
            (self.participant, 403),
            (self.outsider, 403),
        ):
            if user:
                self.client.force_login(user)
            response = self.client.post(url, data)
            self.assertEqual(
                response.status_code,
                status,
                f"{user} action returned wrong response code",
            )

    def test_create_no_method_name(self):
        url = reverse("poll-list")
        data = {
            "title": "Let's vote",
            "meeting": self.meeting.pk,
            "agenda_item": self.ai.pk,
            "proposals": [self.prop.pk],
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("method_name", response.json())

    def test_list_poll_in_this_meeting(self):
        poll = self.meeting.polls.create(
            agenda_item=self.ai, method_name="simple", state="upcoming"
        )
        url = f"/api/polls/?agenda_item={self.ai.pk}"
        self.moderator.is_superuser = True
        self.moderator.save()
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(1, len(data))
        self.assertEqual(poll.pk, data[0]["pk"])
        # Participant
        self.client.force_login(self.participant)
        response = self.client.get(url)
        self.assertEqual(1, len(response.json()))
        # Authenticated but not within meeting
        self.client.force_login(self.outsider)
        response = self.client.get(url)
        self.assertEqual(0, len(response.json()))

    def test_get(self):
        poll = self.meeting.polls.create(
            agenda_item=self.ai, method_name="simple", state="upcoming"
        )
        url = f"/api/polls/{poll.pk}/"
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(poll.pk, data["pk"])
        # Participant
        self.client.force_login(self.participant)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        # Authenticated but not within meeting
        self.client.force_login(self.outsider)
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)

    def test_get_private_ai(self):
        poll = self.meeting.polls.create(
            agenda_item=self.ai_private, method_name="simple", state="upcoming"
        )
        url = f"/api/polls/{poll.pk}/"
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(poll.pk, data["pk"])
        # Participant
        self.client.force_login(self.participant)
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)
        # Authenticated but not within meeting
        self.client.force_login(self.outsider)
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)

    def test_get_private_poll(self):
        poll = self.meeting.polls.create(agenda_item=self.ai, method_name="simple")
        url = f"/api/polls/{poll.pk}/"
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        # Participant
        self.client.force_login(self.participant)
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)
        # Authenticated but not within meeting
        self.client.force_login(self.outsider)
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)

    def test_get_other_meeting(self):
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        poll = meeting.polls.create(method_name="simple", state="upcoming")
        url = f"/api/polls/{poll.pk}/"
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)
        # Participant
        self.client.force_login(self.participant)
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)
        # Authenticated but not within meeting
        self.client.force_login(self.outsider)
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)

    def test_change(self):
        poll = self.meeting.polls.create(method_name="simple", title="First")
        url = f"/api/polls/{poll.pk}/"
        self.client.force_login(self.moderator)
        data = {"title": "And then"}  # Readonly
        response = self.client.patch(url, data)
        self.assertEqual(200, response.status_code)
        poll.refresh_from_db(fields=("title",))
        self.assertEqual("First", poll.title)


class ElectoralRegisterViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting",
        )
        cls.participant: User = User.objects.create_user("participant")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.er = cls.meeting.electoral_registers.create()

    def test_list(self):
        url = reverse("electoral-registers-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(1, len(data))

    def test_get(self):
        url = reverse("electoral-registers-detail", kwargs={"pk": self.er.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(self.er.pk, data["pk"])
