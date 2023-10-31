from json import dumps

from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.workflows import MeetingWf
from voteit.poll.app.er_policies.auto_always import AutoAlways
from voteit.poll.app.polls.combined_simple import CombinedSimple
from voteit.poll.workflows import PollWf
from voteit.proposal.workflows import ProposalWf

User = get_user_model()


class PollViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting",
        )
        cls.ai = cls.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        cls.ai_private = cls.meeting.agenda_items.create(title="Private")
        cls.prop = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.prop3 = cls.ai.proposals.create()
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
            "p_ord": "a",
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual("a", data["p_ord"])

    def test_create_very_long_title(self):
        url = reverse("poll-list")
        data = {
            "title": "A" * 200,
            "meeting": self.meeting.pk,
            "method_name": "simple",
            "agenda_item": self.ai.pk,
            "proposals": [self.prop.pk],
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertContains(response, "title", status_code=400)

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

    def test_create_repeated_schulze_sort(self):
        from voteit.poll.app.polls.schulze import RepeatedSchulze

        url = reverse("poll-list")
        data = {
            "title": "Let's vote",
            "meeting": self.meeting.pk,
            "agenda_item": self.ai.pk,
            "proposals": [self.prop.pk, self.prop2.pk, self.prop3.pk],
            "method_name": RepeatedSchulze.name,
            "settings": {"winners": ""},
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)
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
        url = reverse("poll-detail", kwargs={"pk": poll.pk})
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
        url = reverse("poll-detail", kwargs={"pk": poll.pk})
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
        meeting = Meeting.objects.create()
        poll = meeting.polls.create(method_name="simple", state="upcoming")
        url = reverse("poll-detail", kwargs={"pk": poll.pk})
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
        url = reverse("poll-detail", kwargs={"pk": poll.pk})
        self.client.force_login(self.moderator)
        data = {"title": "And then"}  # Readonly
        response = self.client.patch(url, data)
        self.assertEqual(200, response.status_code)
        poll.refresh_from_db(fields=("title",))
        self.assertEqual("First", poll.title)

    def test_transition_without_register(self):
        poll = self.meeting.polls.create(
            method_name="simple", title="First", state="upcoming"
        )
        self.meeting.electoral_registers.create()
        url = reverse("poll-transitions", kwargs={"pk": poll.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url, data={"transition": "ongoing"})
        self.assertContains(
            response, "no electoral register method on this meeting", status_code=400
        )

    def test_publish_result(self):
        self.meeting.add_roles(self.participant, ROLE_POTENTIAL_VOTER)
        self.meeting.er_policy_name = AutoAlways.name
        self.meeting.state = MeetingWf.ONGOING
        self.meeting.save()
        self.meeting.er_policy.create_er()
        poll = self.meeting.polls.create(
            method_name=CombinedSimple.name,
            title="First",
            state="upcoming",
            withheld_result=True,
        )
        poll.proposals.add(self.prop)
        poll.ongoing()
        poll.save()
        poll.votes.create(user=self.participant, vote=f'{{"yes": [{self.prop.pk}]}}')

        url = reverse("poll-transitions", kwargs={"pk": poll.pk})
        self.client.force_login(self.moderator)
        # Close poll
        response = self.client.post(url, data={"transition": "close"})
        self.assertEqual(201, response.status_code)
        self.assertEqual({"state": PollWf.WITHHELD}, response.json())
        self.prop.refresh_from_db()
        self.assertEqual(ProposalWf.VOTING, self.prop.state)
        poll.refresh_from_db()
        self.assertEqual(PollWf.WITHHELD, poll.state)
        # Publish result
        response = self.client.post(url, data={"transition": "publish_result"})
        self.assertEqual(201, response.status_code)
        self.assertEqual({"state": PollWf.FINISHED}, response.json())
        self.prop.refresh_from_db()
        self.assertEqual(ProposalWf.APPROVED, self.prop.state)
        poll.refresh_from_db()
        self.assertEqual(PollWf.FINISHED, poll.state)


class ElectoralRegisterViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import ElectoralRegister

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting",
        )
        cls.participant: User = User.objects.create_user("participant")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.er: ElectoralRegister = cls.meeting.electoral_registers.create()
        cls.er.set_voters_from_dict({cls.moderator.pk: 1, cls.participant.pk: 2})

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
        self.assertIsInstance(data["weights"], list)
        self.assertEqual(2, len(data["weights"]))
        self.assertEqual(
            [
                {"user": self.participant.pk, "weight": 2},
                {"user": self.moderator.pk, "weight": 1},
            ],
            sorted(data["weights"], key=lambda x: x["user"]),
        )


class ExportElectoralRegisterViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import ElectoralRegister

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting",
        )
        cls.participant: User = User.objects.create_user(
            "participant", first_name="Jeff", userid="jeffrey", email="jeff@none.com"
        )
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.er: ElectoralRegister = cls.meeting.electoral_registers.create()
        cls.er.set_voters_from_dict({cls.moderator.pk: 1, cls.participant.pk: 2})

    def test_not_allowed(self):
        self.client.force_login(self.outsider)
        url = reverse("export-electoral-register-json", kwargs={"pk": self.er.pk})
        response = self.client.get(url)
        self.assertContains(
            response, "permission meeting.moderate_meeting", status_code=403
        )

    def test_csv_no_data(self):
        self.er.voterweight_set.all().delete()
        self.client.force_login(self.moderator)
        url = reverse("export-electoral-register-csv", kwargs={"pk": self.er.pk})
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

    def test_json(self):
        url = reverse("export-electoral-register-json", kwargs={"pk": self.er.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(2, len(data))
        self.assertEqual(
            {
                "first_name": "Jeff",
                "last_name": "",
                "email": "jeff@none.com",
                "userid": "jeffrey",
                "weight": 2,
            },
            data[1],
        )

    def test_csv(self):
        url = reverse("export-electoral-register-csv", kwargs={"pk": self.er.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual("text/csv", response.headers.get("Content-Type"))
        self.assertEqual(
            f'attachment; filename="er_{self.er.pk}_export.csv"',
            response.headers.get("Content-Disposition"),
        )
        rows = response.content.splitlines()
        self.assertEqual(b"first_name,last_name,email,userid,weight", rows[0])
        self.assertEqual(b"Jeff,,jeff@none.com,jeffrey,2", rows[2])


class ElectoralRegisterPolicyViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="user")

    def test_list(self):
        self.client.force_login(self.user)
        response = self.client.get("/api/electoral-register-policies/")
        self.assertEqual(200, response.status_code)
        data = response.json()
        data = sorted(data, key=lambda x: x["name"])
        first = data[0]
        self.assertTrue(first.pop("description"))
        self.assertEqual(
            {
                "available": True,
                "allow_manual": False,
                "require_manual": False,
                "allow_poll_er_change": True,
                "allow_trigger": False,
                "group_votes_active": False,
                "handles_vote_weight": False,
                "handles_active_check": False,
                "handles_delegate_to": False,
                "name": "auto_always",
                "title": "Automatic always",
            },
            first,
        )
