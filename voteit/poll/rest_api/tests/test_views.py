from unittest.mock import patch

from django.core.exceptions import ObjectDoesNotExist
from django.test import override_settings
from django.contrib.auth import get_user_model
from envelope.testing import testing_channel_layers_setting
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.core.testing import run_permission_tests
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.workflows import MeetingWf
from voteit.poll.app.er_policies.auto_always import AutoAlways
from voteit.poll.app.polls.combined_simple import CombinedSimple
from voteit.poll.app.polls.schulze import RepeatedSchulze
from voteit.poll.messages import ManualCreateER
from voteit.poll.models import ElectoralRegister
from voteit.poll.registries import er_policy
from voteit.poll.registries import vote_transfer_policies
from voteit.poll.testing import UnrestrictedVoteTransferER
from voteit.poll.testing import UnrestrictedVoteTransferPolicy
from voteit.poll.workflows import PollWf
from voteit.proposal.workflows import ProposalWf

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
        self.meeting.er_policy_name = ManualCreateER.name
        self.meeting.save()
        poll = self.meeting.polls.create(
            method_name="simple", title="First", state="upcoming"
        )
        poll.proposals.add(self.prop)
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
        # FIXME: assert queries! N+1!
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
        self.assertEqual(400, response.status_code)
