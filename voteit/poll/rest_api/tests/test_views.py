from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.test import override_settings
from django.utils import timezone
from voteit.messaging.channels import UserChannel
from voteit.messaging.testing import ChannelMessageCatcher
from voteit.messaging.testing import testing_channel_layers_setting
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.core.testing import run_permission_tests
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.statemachines import MeetingStateMachine
from voteit.poll.app.er_policies.auto_always import AutoAlways
from voteit.poll.app.er_policies.auto_before_poll import AutoBeforePoll
from voteit.poll.app.er_policies.manual import Manual
from voteit.poll.app.polls.combined_simple import CombinedSimple
from voteit.poll.app.polls.majority import Majority
from voteit.poll.app.polls.schulze import RepeatedSchulze
from voteit.poll.app.polls.schulze import Schulze
from voteit.poll.messages import GenericVoteResponse
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.poll.registries import er_policy
from voteit.poll.registries import vote_transfer_policies
from voteit.poll.testing import UnrestrictedVoteTransferER
from voteit.poll.testing import UnrestrictedVoteTransferPolicy

User = get_user_model()


class PollViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.ai = cls.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        cls.ai_private = cls.meeting.agenda_items.create(title="Private")
        cls.prop = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.prop3 = cls.ai.proposals.create()
        cls.participant: User = User.objects.get(username="participant")
        cls.moderator: User = User.objects.get(username="moderator")
        cls.outsider: User = User.objects.create_user("outsider")

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

    def test_create(self):
        data = {
            "title": "Let's vote",
            "meeting": self.meeting.pk,
            "method_name": "simple",
            "agenda_item": self.ai.pk,
            "proposals": [self.prop.pk],
        }
        for func, args in run_permission_tests(
            self,
            url=reverse("poll-list"),
            data=data,
            method="POST",
            expected=[
                [None, 401],
                [self.participant, 403],
                [self.outsider, 403],
                [self.moderator, 201, data],
            ],
        ):
            func(*args)

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
            agenda_item=self.ai,
            method_name="simple",
            state="upcoming",
            title="A visible poll",
        )
        poll.proposals.add(self.prop)
        for func, args in run_permission_tests(
            self,
            url=reverse("poll-detail", kwargs={"pk": poll.id}),
            method="get",
            expected=[
                [None, 401],
                [self.participant, 200],
                [self.outsider, 404],
                [
                    self.moderator,
                    200,
                    {
                        "title": "A visible poll",
                        "meeting": self.meeting.pk,
                        "method_name": "simple",
                        "state": "upcoming",
                        "agenda_item": self.ai.pk,
                        "proposals": [self.prop.pk],
                        "pk": poll.pk,
                    },
                ],
            ],
        ):
            func(*args)

    def test_get_private_ai(self):
        poll = self.meeting.polls.create(
            agenda_item=self.ai_private,
            method_name="simple",
            state="upcoming",
            title="With private AI",
        )
        poll.proposals.add(self.prop)
        for func, args in run_permission_tests(
            self,
            url=reverse("poll-detail", kwargs={"pk": poll.id}),
            method="get",
            expected=[
                [None, 401],
                [self.participant, 404],
                [self.outsider, 404],
                [
                    self.moderator,
                    200,
                    {
                        "title": "With private AI",
                        "meeting": self.meeting.pk,
                        "method_name": "simple",
                        "agenda_item": self.ai_private.pk,
                        "proposals": [self.prop.pk],
                        "pk": poll.pk,
                    },
                ],
            ],
        ):
            func(*args)

    def test_get_private_poll(self):
        poll = self.meeting.polls.create(
            agenda_item=self.ai,
            method_name="simple",
            title="Private poll",
        )
        poll.proposals.add(self.prop)
        for func, args in run_permission_tests(
            self,
            url=reverse("poll-detail", kwargs={"pk": poll.id}),
            method="get",
            expected=[
                [None, 401],
                [self.participant, 404],
                [self.outsider, 404],
                [
                    self.moderator,
                    200,
                    {
                        "title": "Private poll",
                        "meeting": self.meeting.pk,
                        "method_name": "simple",
                        "agenda_item": self.ai.pk,
                        "proposals": [self.prop.pk],
                        "pk": poll.pk,
                    },
                ],
            ],
        ):
            func(*args)

    def test_get_other_meeting(self):
        meeting = Meeting.objects.create()
        poll = meeting.polls.create(
            method_name="simple", state="upcoming", title="Other meetings poll"
        )
        for func, args in run_permission_tests(
            self,
            url=reverse("poll-detail", kwargs={"pk": poll.id}),
            method="get",
            expected=[
                [None, 401],
                [self.participant, 404],
                [self.outsider, 404],
                [self.moderator, 404],
            ],
        ):
            func(*args)

    def test_change(self):
        poll = self.meeting.polls.create(method_name="simple", title="First")
        for func, args in run_permission_tests(
            self,
            url=reverse("poll-detail", kwargs={"pk": poll.id}),
            method="patch",
            data={"title": "And then"},
            expected=[
                [self.participant, 404],
                [self.outsider, 404],
                [
                    self.moderator,
                    200,
                    {
                        "title": "And then",
                        "pk": poll.pk,
                    },
                ],
            ],
        ):
            func(*args)

    def test_transition_without_register(self):
        self.meeting.er_policy_name = "er.manual_create"  # invalid policy name
        self.meeting.save()
        poll = self.meeting.polls.create(
            method_name="simple", title="First", state="upcoming"
        )
        poll.proposals.add(self.prop)
        url = reverse("poll-event", kwargs={"pk": poll.pk})
        self.client.force_login(self.moderator)
        response = self.client.post(url, data={"event": "make_ongoing"})
        data = response.json()
        self.assertEqual(response.status_code, 400, data)
        self.assertEqual({"event": "Poll has no electoral register."}, data)

    def test_publish_result(self):
        self.meeting.add_roles(self.participant, ROLE_POTENTIAL_VOTER)
        self.meeting.er_policy_name = AutoAlways.name
        self.meeting.state = MeetingStateMachine.ongoing.value
        self.meeting.save()
        self.meeting.er_policy.create_er()
        poll = self.meeting.polls.create(
            method_name=CombinedSimple.name,
            title="First",
            state="ongoing",
            started=timezone.now(),
            withheld_result=True,
            electoral_register=self.meeting.latest_er,
        )
        poll.proposals.add(self.prop)
        self.prop.state = "voting"
        self.prop.save()
        poll.votes.create(user=self.participant, vote=f'{{"yes": [{self.prop.pk}]}}')

        url = reverse("poll-event", kwargs={"pk": poll.pk})
        self.client.force_login(self.moderator)
        # Close poll
        response = self.client.post(url, data={"event": "close"})
        self.assertEqual(200, response.status_code)
        self.assertEqual("withheld", response.json()["state"])
        self.prop.refresh_from_db()
        self.assertEqual("voting", self.prop.state)
        poll.refresh_from_db()
        self.assertEqual("withheld", poll.state)
        # Publish result
        response = self.client.post(url, data={"event": "publish_result"})
        self.assertEqual(200, response.status_code)
        self.assertEqual("finished", response.json()["state"])
        self.prop.refresh_from_db()
        self.assertEqual("approved", self.prop.state)
        poll.refresh_from_db()
        self.assertEqual("finished", poll.state)


class ElectoralRegisterViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting",
        )
        cls.moderator: User = User.objects.create_user("moderator")
        cls.voters = []
        for i in range(5):
            voter = User.objects.create_user(f"voter_{i}")
            cls.meeting.add_roles(voter, ROLE_PARTICIPANT, ROLE_POTENTIAL_VOTER)
            cls.voters.append(voter)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR, ROLE_POTENTIAL_VOTER)
        cls.er: ElectoralRegister = cls.meeting.electoral_registers.create()
        cls.voter_weights = {cls.moderator.pk: 1, **{v.pk: 2 for v in cls.voters}}
        cls.er.set_voters_from_dict(cls.voter_weights)
        for i in range(3):
            er = cls.meeting.electoral_registers.create()
            er.set_voters_from_dict(cls.voter_weights)

    def test_list(self):
        url = reverse("electoral-registers-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url, data={"meeting": self.meeting.pk})
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(4, len(data))

    def test_get(self):
        url = reverse("electoral-registers-detail", kwargs={"pk": self.er.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(self.er.pk, data["pk"])
        self.assertIsInstance(data["weights"], list)
        self.assertEqual(6, len(data["weights"]))
        self.assertEqual(
            self.voter_weights, {x["user"]: x["weight"] for x in data["weights"]}
        )

    def test_cache(self):
        url = reverse("electoral-registers-detail", kwargs={"pk": self.er.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual("max-age=604800", response.headers.get("Cache-Control"))


class ExportElectoralRegisterViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
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
        self.assertEqual(404, response.status_code)

    def test_csv_no_data(self):
        self.er.voter_data = {}
        self.er.save()
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
                "vote_transfer_policy": None,
            },
            first,
        )


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
@patch.dict(
    vote_transfer_policies,
    {UnrestrictedVoteTransferPolicy.name: UnrestrictedVoteTransferPolicy},
)
@patch.dict(
    er_policy,
    {UnrestrictedVoteTransferER.name: UnrestrictedVoteTransferER},
)
class VoteTransferViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.meeting.er_policy_name = UnrestrictedVoteTransferER.name
        cls.meeting.save()
        cls.participant = cls.meeting.participants.get(username="participant")
        cls.voter = cls.meeting.participants.create(username="voter")
        cls.other_participant = cls.meeting.participants.create(username="other")
        cls.moderator = cls.meeting.participants.get(username="moderator")
        cls.meeting.add_roles(cls.voter, ROLE_POTENTIAL_VOTER)
        # And another meeting
        cls.other_meeting = Meeting.objects.create()
        cls.user_in_another_meeting = cls.other_meeting.participants.create(
            username="user_in_another_meeting"
        )

    def test_transfer_own(self):
        self.client.force_login(self.voter)
        url = reverse("vote-transfer-list")
        data = {
            "meeting": self.meeting.pk,
            "source": self.voter.pk,
            "target": self.other_participant.pk,
        }
        response = self.client.post(
            url,
            data=data,
        )
        response_data = response.json()
        response_data.pop("pk")
        self.assertEqual(data, response_data)
        self.assertEqual(201, response.status_code)

    def test_transfer_own_non_voter(self):
        self.client.force_login(self.participant)
        url = reverse("vote-transfer-list")
        data = {
            "meeting": self.meeting.pk,
            "source": self.participant.pk,
            "target": self.other_participant.pk,
        }
        response = self.client.post(url, data=data)
        self.assertDictEqual(
            {
                "detail": "You're missing the permission 'poll.add_votetransfer' on Testfixture meeting."
            },
            response.json(),
        )
        self.assertEqual(403, response.status_code)

    def test_transfer_others_regular_user(self):
        self.client.force_login(self.voter)
        url = reverse("vote-transfer-list")
        data = {
            "meeting": self.meeting.pk,
            "source": self.participant.pk,
            "target": self.other_participant.pk,
        }
        response = self.client.post(url, data=data)
        self.assertEqual(
            {"source": ["You can't delegate votes unless you're a moderator"]},
            response.json(),
        )
        self.assertEqual(400, response.status_code)

    def test_transfer_others_moderator(self):
        self.client.force_login(self.moderator)
        url = reverse("vote-transfer-list")
        data = {
            "meeting": self.meeting.pk,
            "source": self.voter.pk,
            "target": self.other_participant.pk,
        }
        response = self.client.post(url, data=data)
        response_data = response.json()
        response_data.pop("pk")
        self.assertEqual(
            response_data,
            response.json(),
        )
        self.assertEqual(201, response.status_code)

    def test_transfer_source_duplicate(self):
        self.client.force_login(self.voter)
        url = reverse("vote-transfer-list")
        data = {
            "meeting": self.meeting.pk,
            "source": self.voter.pk,
            "target": self.participant.pk,
        }
        response = self.client.post(url, data=data)
        response_data = response.json()
        response_data.pop("pk")
        self.assertEqual(data, response_data)
        self.assertEqual(201, response.status_code)
        # And again to other user
        data = {
            "meeting": self.meeting.pk,
            "source": self.voter.pk,
            "target": self.other_participant.pk,
        }
        response = self.client.post(url, data=data)
        self.assertEqual(
            {
                "non_field_errors": [
                    "The fields source, meeting must make a unique set."
                ]
            },
            response.json(),
        )
        self.assertEqual(400, response.status_code)

    def test_transfer_to_self(self):
        self.client.force_login(self.voter)
        url = reverse("vote-transfer-list")
        data = {
            "meeting": self.meeting.pk,
            "source": self.voter.pk,
            "target": self.voter.pk,
        }
        response = self.client.post(url, data=data)
        self.assertEqual({"target": ["target is same as source"]}, response.json())
        self.assertEqual(400, response.status_code)

    def test_delete_own(self):
        self.client.force_login(self.voter)
        transfer = self.meeting.vote_transfers.create(
            source=self.voter, target=self.participant
        )
        url = reverse("vote-transfer-detail", kwargs={"pk": transfer.pk})
        response = self.client.delete(url)
        self.assertEqual(204, response.status_code)
        with self.assertRaises(ObjectDoesNotExist):
            transfer.refresh_from_db()

    def test_delete_others(self):
        self.client.force_login(self.other_participant)
        transfer = self.meeting.vote_transfers.create(
            source=self.voter, target=self.participant
        )
        url = reverse("vote-transfer-detail", kwargs={"pk": transfer.pk})
        response = self.client.delete(url)
        self.assertEqual(404, response.status_code)

    def test_delete_others_moderator(self):
        self.client.force_login(self.moderator)
        transfer = self.meeting.vote_transfers.create(
            source=self.voter, target=self.participant
        )
        url = reverse("vote-transfer-detail", kwargs={"pk": transfer.pk})
        response = self.client.delete(url)
        self.assertEqual(204, response.status_code)

    def test_target_from_another_meeting_where_source_isnt(self):
        self.client.force_login(self.voter)
        url = reverse("vote-transfer-list")
        data = {
            "meeting": self.meeting.pk,
            "source": self.voter.pk,
            "target": self.user_in_another_meeting.pk,
        }
        response = self.client.post(url, data=data)
        self.assertEqual(
            {
                "target": [
                    f'Invalid pk "{self.user_in_another_meeting.pk}" - object does not exist.'
                ]
            },
            response.json(),
        )
        self.assertEqual(400, response.status_code)

    def test_target_from_another_meeting(self):
        self.client.force_login(self.voter)
        self.other_meeting.add_roles(self.voter, ROLE_POTENTIAL_VOTER)
        url = reverse("vote-transfer-list")
        data = {
            "meeting": self.meeting.pk,
            "source": self.voter.pk,
            "target": self.user_in_another_meeting.pk,
        }
        response = self.client.post(url, data=data)
        self.assertEqual(
            {"target": ["target user isn't in the same meeting as the source user"]},
            response.json(),
        )
        self.assertEqual(400, response.status_code)

    def test_target_delegates_to_other(self):
        transfer = self.meeting.vote_transfers.create(
            source=self.voter, target=self.participant
        )
        self.client.force_login(self.participant)
        url = reverse("vote-transfer-detail", kwargs={"pk": transfer.pk})
        response = self.client.patch(url, data={"target": self.other_participant.pk})
        self.assertEqual(self.other_participant.pk, response.json()["target"])
        self.assertEqual(200, response.status_code)

    def test_source_delegates_to_other(self):
        transfer = self.meeting.vote_transfers.create(
            source=self.voter, target=self.participant
        )
        self.client.force_login(self.voter)
        url = reverse("vote-transfer-detail", kwargs={"pk": transfer.pk})
        response = self.client.patch(url, data={"target": self.other_participant.pk})
        self.assertEqual(self.other_participant.pk, response.json()["target"])
        self.assertEqual(200, response.status_code)

    def test_moderator_delegates_to_other(self):
        transfer = self.meeting.vote_transfers.create(
            source=self.voter, target=self.participant
        )
        self.client.force_login(self.moderator)
        url = reverse("vote-transfer-detail", kwargs={"pk": transfer.pk})
        response = self.client.patch(url, data={"target": self.other_participant.pk})
        self.assertEqual(self.other_participant.pk, response.json()["target"])
        self.assertEqual(200, response.status_code)

    def test_moderator_delegates_to_user_from_another_meeting(self):
        transfer = self.meeting.vote_transfers.create(
            source=self.voter, target=self.participant
        )
        self.client.force_login(self.moderator)
        url = reverse("vote-transfer-detail", kwargs={"pk": transfer.pk})
        response = self.client.patch(
            url, data={"target": self.user_in_another_meeting.pk}
        )
        self.assertEqual(
            {
                "target": [
                    f'Invalid pk "{self.user_in_another_meeting.pk}" - object does not exist.'
                ]
            },
            response.json(),
        )


class TriggerCreateERViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Trigger ER test meeting",
            er_policy_name=AutoBeforePoll.name,
            state="ongoing",
        )
        cls.moderator: User = User.objects.create_user("trigger_er_moderator")
        cls.participant: User = User.objects.create_user("trigger_er_participant")
        cls.voter: User = User.objects.create_user("trigger_er_voter")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.voter, ROLE_PARTICIPANT, ROLE_POTENTIAL_VOTER)
        cls.url = reverse("electoral-registers-trigger-create")

    def test_creates_er(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.url, data={"meeting": self.meeting.pk}, format="json"
        )
        self.assertEqual(201, response.status_code)
        data = response.json()
        self.assertEqual(self.meeting.pk, data["meeting"])
        self.assertIn("pk", data)
        self.assertIn("weights", data)
        self.assertEqual(1, self.meeting.electoral_registers.count())

    def test_creates_if_changed(self):
        self.client.force_login(self.moderator)
        self.client.post(self.url, data={"meeting": self.meeting.pk}, format="json")
        response = self.client.post(
            self.url, data={"meeting": self.meeting.pk}, format="json"
        )
        self.assertEqual(204, response.status_code)

    def test_participant_gets_400(self):
        self.client.force_login(self.participant)
        response = self.client.post(
            self.url, data={"meeting": self.meeting.pk}, format="json"
        )
        self.assertContains(response, "object does not exist", status_code=400)

    def test_trigger_not_allowed_for_manual_policy(self):
        self.meeting.er_policy_name = Manual.name
        self.meeting.save()
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.url, data={"meeting": self.meeting.pk}, format="json"
        )
        data = response.json()
        self.assertEqual(400, response.status_code, data)
        self.assertEqual(
            {"meeting": ["Electoral register can't be triggered this way"]}, data
        )

    def test_no_valid_policy(self):
        self.meeting.er_policy_name = None
        self.meeting.save()
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.url, data={"meeting": self.meeting.pk}, format="json"
        )
        data = response.json()
        self.assertEqual(400, response.status_code, data)
        self.assertEqual(
            {"meeting": ["Electoral register settings missing for this meeting."]}, data
        )

    def test_meeting_not_ongoing(self):
        self.meeting.make_upcoming(self.moderator)
        self.meeting.save()
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.url, data={"meeting": self.meeting.pk}, format="json"
        )
        data = response.json()
        self.assertEqual(400, response.status_code, data)
        self.assertEqual({"meeting": ["Meeting isn't ongoing"]}, data)


class ManualCreateERViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Manual ER test meeting",
            state="ongoing",
            er_policy_name=Manual.name,
        )
        cls.moderator: User = User.objects.create_user("manual_er_moderator")
        cls.participant: User = User.objects.create_user("manual_er_participant")
        cls.voter: User = User.objects.create_user("manual_er_voter")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.voter, ROLE_PARTICIPANT, ROLE_POTENTIAL_VOTER)
        cls.url = reverse("electoral-registers-manual-create")
        cls.weights = [
            {"user": cls.moderator.pk, "weight": 1},
            {"user": cls.voter.pk, "weight": 2},
        ]

    def test_creates_er(self):
        response = self.client.post(
            self.url,
            data={"meeting": self.meeting.pk, "weights": self.weights},
            format="json",
        )
        self.assertEqual(401, response.status_code)
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.url,
            data={"meeting": self.meeting.pk, "weights": self.weights},
            format="json",
        )
        self.assertEqual(201, response.status_code)
        data = response.json()
        self.assertEqual(self.meeting.pk, data["meeting"])
        self.assertIn("pk", data)
        weight_dict = {w["user"]: w["weight"] for w in data["weights"]}
        self.assertEqual({self.moderator.pk: 1, self.voter.pk: 2}, weight_dict)

    def test_no_new_er_returns_204(self):
        self.client.force_login(self.moderator)
        payload = {"meeting": self.meeting.pk, "weights": self.weights}
        self.client.post(self.url, data=payload, format="json")
        response = self.client.post(self.url, data=payload, format="json")
        self.assertEqual(204, response.status_code)

    def test_participant_gets_400(self):
        self.client.force_login(self.participant)
        response = self.client.post(
            self.url,
            data={"meeting": self.meeting.pk, "weights": self.weights},
            format="json",
        )
        self.assertContains(response, "object does not exist", status_code=400)

    def test_bad_user_in_weights_gets_400(self):
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.url,
            data={"meeting": self.meeting.pk, "weights": [{"user": 0, "weight": 1}]},
            format="json",
        )
        self.assertContains(response, "invalid potential voters", status_code=400)

    def test_non_manual_policy_gets_400(self):
        self.meeting.er_policy_name = AutoBeforePoll.name
        self.meeting.save()
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.url,
            data={"meeting": self.meeting.pk, "weights": self.weights},
            format="json",
        )
        self.assertContains(
            response, "Electoral register can't be manually created", status_code=400
        )

    def test_upcoming_meeting_gets_400(self):
        self.meeting.make_upcoming(self.moderator)
        self.meeting.save()
        self.client.force_login(self.moderator)
        response = self.client.post(
            self.url,
            data={"meeting": self.meeting.pk, "weights": self.weights},
            format="json",
        )
        self.assertContains(response, "Meeting isn't ongoing", status_code=400)


class PollStateMachineSchemaTests(APITestCase):
    def test_detail(self):
        response = self.client.get("/api/state-machines/PollStateMachine/")
        self.assertEqual(200, response.status_code)
        self.assertIn("states", response.data)
        self.assertIn("events", response.data)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class VoteViewSetTests(APITestCase):
    """Covers the add/change/abstain vote upsert, previously the AddVote/AbstainVote
    WS messages. Uses the "simple" poll method as the base, same as the old tests.
    """

    @classmethod
    def setUpTestData(cls):
        # No meeting attached - same as the old message-based tests. Keeps the
        # state machine's meeting/AI/ER-policy guards out of scope (see
        # PollStateMachine's "Skip for unittests" branches) since this class
        # only exercises the vote add/abstain upsert and permission checks.
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.voter: User = User.objects.create(username="voter")
        cls.outsider: User = User.objects.create(username="outsider")
        cls.er.set_voters_from_dict({cls.voter.pk: 1})
        cls.poll: Poll = Poll.objects.create(
            electoral_register=cls.er, method_name="simple"
        )
        cls.poll.proposals.create()
        cls.poll.upcoming(force=True)
        cls.poll.save()

    def setUp(self):
        self.poll.refresh_from_db()

    def _url(self):
        return reverse("vote-list")

    def test_permissions(self):
        self.poll.ongoing(force=True)
        self.poll.save()
        data = {"poll": self.poll.pk, "vote": {"choice": "yes"}}
        for func, args in run_permission_tests(
            self,
            url=self._url(),
            data=data,
            method="post",
            expected=[
                [None, 401],
                [self.outsider, 403],
                [self.voter, 201],
            ],
        ):
            func(*args)

    def test_add_not_started(self):
        self.client.force_login(self.voter)
        response = self.client.post(
            self._url(),
            {"poll": self.poll.pk, "vote": {"choice": "yes"}},
            format="json",
        )
        self.assertEqual(403, response.status_code)

    def test_add_closed_poll(self):
        self.poll.ongoing(force=True)
        self.poll.close(force=True)
        self.poll.save()
        self.client.force_login(self.voter)
        response = self.client.post(
            self._url(),
            {"poll": self.poll.pk, "vote": {"choice": "yes"}},
            format="json",
        )
        self.assertEqual(403, response.status_code)

    def test_add_and_change(self):
        self.poll.ongoing(force=True)
        self.poll.save()
        self.client.force_login(self.voter)
        response = self.client.post(
            self._url(),
            {"poll": self.poll.pk, "vote": {"choice": "yes"}},
            format="json",
        )
        self.assertEqual(201, response.status_code)
        vote = self.poll.votes.get(user=self.voter)
        self.assertEqual("yes", vote.vote_data)
        # Casting again updates the same row (upsert - there's no separate "change")
        response = self.client.post(
            self._url(),
            {"poll": self.poll.pk, "vote": {"choice": "no"}},
            format="json",
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, self.poll.votes.filter(user=self.voter).count())
        vote.refresh_from_db()
        self.assertEqual({"choice": "no"}, vote.vote.dict())

    def test_add_vote_exists(self):
        self.poll.ongoing(force=True)
        self.poll.save()
        self.poll.votes.create(user=self.voter, vote_data="no")
        self.client.force_login(self.voter)
        response = self.client.post(
            self._url(),
            {"poll": self.poll.pk, "vote": {"choice": "yes"}},
            format="json",
        )
        self.assertEqual(200, response.status_code)
        vote = self.poll.votes.get(user=self.voter)
        self.assertEqual("yes", vote.vote_data)

    def test_abstain(self):
        self.poll.ongoing(force=True)
        self.poll.save()
        self.client.force_login(self.voter)
        response = self.client.post(
            self._url(), {"poll": self.poll.pk, "abstain": True}, format="json"
        )
        self.assertEqual(201, response.status_code)
        vote = self.poll.votes.get(user=self.voter)
        self.assertIsNone(vote.vote_data)
        self.assertIs(vote.abstain, True)

    def test_abstain_overwrites_existing_vote(self):
        self.poll.ongoing(force=True)
        self.poll.save()
        self.client.force_login(self.voter)
        self.client.post(
            self._url(),
            {"poll": self.poll.pk, "vote": {"choice": "yes"}},
            format="json",
        )
        response = self.client.post(
            self._url(), {"poll": self.poll.pk, "abstain": True}, format="json"
        )
        self.assertEqual(200, response.status_code)
        vote = self.poll.votes.get(user=self.voter)
        self.assertIsNone(vote.vote_data)
        self.assertIs(vote.abstain, True)

    def test_vote_overwrites_existing_abstain(self):
        self.poll.ongoing(force=True)
        self.poll.save()
        self.poll.votes.create(user=self.voter, abstain=True)
        self.client.force_login(self.voter)
        response = self.client.post(
            self._url(),
            {"poll": self.poll.pk, "vote": {"choice": "yes"}},
            format="json",
        )
        self.assertEqual(200, response.status_code)
        vote = self.poll.votes.get(user=self.voter)
        self.assertEqual("yes", vote.vote_data)
        self.assertIs(vote.abstain, False)

    def test_bad_vote_shape(self):
        self.poll.ongoing(force=True)
        self.poll.save()
        self.client.force_login(self.voter)
        response = self.client.post(
            self._url(),
            {"poll": self.poll.pk, "vote": {"choice": "banana"}},
            format="json",
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("vote", response.json())
        self.assertFalse(self.poll.votes.filter(user=self.voter).exists())

    def test_vote_not_an_object(self):
        self.poll.ongoing(force=True)
        self.poll.save()
        self.client.force_login(self.voter)
        response = self.client.post(
            self._url(), {"poll": self.poll.pk, "vote": ["yes"]}, format="json"
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("vote", response.json())

    def test_missing_vote_when_not_abstaining(self):
        self.poll.ongoing(force=True)
        self.poll.save()
        self.client.force_login(self.voter)
        response = self.client.post(self._url(), {"poll": self.poll.pk}, format="json")
        self.assertEqual(400, response.status_code)
        self.assertIn("vote", response.json())

    def test_vote_and_abstain_together_rejected(self):
        self.poll.ongoing(force=True)
        self.poll.save()
        self.client.force_login(self.voter)
        response = self.client.post(
            self._url(),
            {"poll": self.poll.pk, "vote": {"choice": "yes"}, "abstain": True},
            format="json",
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("vote", response.json())
        self.assertFalse(self.poll.votes.filter(user=self.voter).exists())

    def test_empty_vote_and_abstain_together_rejected(self):
        # An empty dict/list is falsy in Python - make sure that doesn't let
        # a malformed "both vote and abstain" request slip past the guard.
        self.poll.ongoing(force=True)
        self.poll.save()
        self.client.force_login(self.voter)
        response = self.client.post(
            self._url(),
            {"poll": self.poll.pk, "vote": {}, "abstain": True},
            format="json",
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("vote", response.json())
        self.assertFalse(self.poll.votes.filter(user=self.voter).exists())

    def test_broadcasts_vote_added(self):
        """
        Broadcasting is done entirely via the Vote/Poll post_save signal
        (signals.py), so it fires the same way regardless of REST vs WS origin.
        (PollStatus is only sent for polls attached to a meeting, out of scope
        for this test class - see the fixture note in setUpTestData.)
        """
        self.poll.ongoing(force=True)
        self.poll.save()
        self.client.force_login(self.voter)
        with ChannelMessageCatcher(UserChannel, GenericVoteResponse) as vote_msgs:
            response = self.client.post(
                self._url(),
                {"poll": self.poll.pk, "vote": {"choice": "yes"}},
                format="json",
            )
        self.assertEqual(201, response.status_code)
        self.assertEqual(1, len(vote_msgs))


class VoteViewSetPollMethodValidationTests(APITestCase):
    """
    PollMethod.validate_vote() is method-specific extra validation (e.g. checking
    that a ranked/chosen vote actually refers to real proposals on the poll).
    Covers the error path for a few methods that override it.
    """

    @classmethod
    def setUpTestData(cls):
        cls.voter: User = User.objects.create(username="voter")
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.er.set_voters_from_dict({cls.voter.pk: 1})

    def _mk_ongoing_poll(self, **kw) -> Poll:
        # Bypass the state machine's start_check() (proposal-count guards
        # unrelated to what's being tested here) - same as the old message-based
        # tests, which used state="ongoing" directly.
        kw.setdefault("state", "ongoing")
        return Poll.objects.create(electoral_register=self.er, **kw)

    def _url(self):
        return reverse("vote-list")

    def test_majority_bad_proposal(self):
        poll = self._mk_ongoing_poll(method_name=Majority.name)
        prop1 = poll.proposals.create()
        poll.proposals.create()
        self.client.force_login(self.voter)
        response = self.client.post(
            self._url(),
            {"poll": poll.pk, "vote": {"choice": prop1.pk - 1000}},
            format="json",
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("vote", response.json())
        self.assertIn("choice", response.json()["vote"])

    def test_schulze_bad_ranking(self):
        poll = self._mk_ongoing_poll(method_name=Schulze.name)
        prop1 = poll.proposals.create()
        poll.proposals.create()
        poll.proposals.create()
        self.client.force_login(self.voter)
        response = self.client.post(
            self._url(),
            {"poll": poll.pk, "vote": {"ranking": [[prop1.pk - 1000, 10]]}},
            format="json",
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("vote", response.json())
        self.assertIn("ranking", response.json()["vote"])
