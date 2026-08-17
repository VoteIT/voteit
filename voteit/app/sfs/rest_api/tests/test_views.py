from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import override_settings
from envelope.testing import testing_channel_layers_setting
from rest_framework.test import APITestCase

from voteit.app.sfs.rest_api.views import DELEGATION_LEADER_ROLE_ID
from voteit.meeting.models import GroupMembership
from voteit.meeting.models import GroupRole
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.app.er_policies.group_votes_before_poll import GroupVotesBeforePoll

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class SetDelegationVotersViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            er_policy_name=GroupVotesBeforePoll.name,
            group_votes_active=True,
            group_roles_active=True,
        )
        cls.leader_role: GroupRole = cls.meeting.group_roles.create(
            role_id=DELEGATION_LEADER_ROLE_ID,
            roles=[ROLE_POTENTIAL_VOTER],
        )
        cls.doctor_hats: MeetingGroup = cls.meeting.groups.create(
            groupid="doctor_hats", votes=4
        )
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR, ROLE_POTENTIAL_VOTER)
        cls.lead_hat = User.objects.create(username="lead_hat")
        cls.hangaround = User.objects.create(username="hangaround")
        cls.meeting.add_roles(cls.hangaround, ROLE_PARTICIPANT, ROLE_POTENTIAL_VOTER)
        cls.mem_lead_hat: GroupMembership = cls.doctor_hats.memberships.create(
            user=cls.lead_hat, role=cls.leader_role
        )
        cls.mem_hangaround: GroupMembership = cls.doctor_hats.memberships.create(
            user=cls.hangaround
        )
        cls.url = reverse("sfs-delegation-voters-set", args=[cls.doctor_hats.pk])

    def _post(self, user, weights: list = ()):
        if user is not None:
            self.client.force_login(user)
        return self.client.post(
            self.url, data={"weights": list(weights)}, format="json"
        )

    def test_set_vote_dist(self):
        weights = [
            {"user": self.lead_hat.pk, "weight": 2},
            {"user": self.hangaround.pk, "weight": 2},
        ]
        response = self._post(self.lead_hat, weights=weights)
        self.assertEqual(200, response.status_code)
        self.assertEqual({"weights": weights}, response.json())
        self.mem_lead_hat.refresh_from_db()
        self.assertEqual(2, self.mem_lead_hat.votes)
        self.mem_hangaround.refresh_from_db()
        self.assertEqual(2, self.mem_hangaround.votes)

    def test_set_vote_dist_with_duplicate_user(self):
        response = self._post(
            self.lead_hat,
            weights=[
                {"user": self.lead_hat.pk, "weight": 2},
                {"user": self.hangaround.pk, "weight": 1},
                {"user": self.hangaround.pk, "weight": 1},
            ],
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            {"weights": [f"Duplicate user entry: {self.hangaround.pk}"]},
            response.json(),
        )

    def test_set_vote_dist_others_cleared(self):
        self.mem_lead_hat.votes = 4
        self.mem_lead_hat.save()
        weights = [{"user": self.hangaround.pk, "weight": 4}]
        response = self._post(self.lead_hat, weights=weights)
        self.assertEqual(200, response.status_code)
        self.assertEqual({"weights": weights}, response.json())
        self.mem_lead_hat.refresh_from_db()
        self.assertIsNone(self.mem_lead_hat.votes)
        self.mem_hangaround.refresh_from_db()
        self.assertEqual(4, self.mem_hangaround.votes)

    def test_anonymous_gets_401(self):
        response = self._post(None, weights=[{"user": self.lead_hat.pk, "weight": 4}])
        self.assertEqual(401, response.status_code)
        self.assertEqual(
            {"detail": "Authentication credentials were not provided."},
            response.json(),
        )

    def test_outsider_gets_403(self):
        outsider = User.objects.create(username="outsider")
        response = self._post(
            outsider, weights=[{"user": self.lead_hat.pk, "weight": 4}]
        )
        self.assertEqual(403, response.status_code)
        self.assertEqual(
            {"detail": "You do not have permission to perform this action."},
            response.json(),
        )

    def test_set_vote_dist_bad_count(self):
        response = self._post(
            self.lead_hat, weights=[{"user": self.lead_hat.pk, "weight": 10}]
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            {"weights": ["Bad vote sum. You've set 10 but the group has 4 votes."]},
            response.json(),
        )

    def test_set_vote_dist_meeting_closed(self):
        self.meeting.state = "closed"
        self.meeting.save()
        response = self._post(
            self.lead_hat,
            weights=[
                {"user": self.lead_hat.pk, "weight": 2},
                {"user": self.hangaround.pk, "weight": 2},
            ],
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual({"non_field_errors": ["Meeting closed."]}, response.json())

    def test_set_vote_dist_no_votes(self):
        self.doctor_hats.votes = None
        self.doctor_hats.save()
        response = self._post(
            self.lead_hat, weights=[{"user": self.lead_hat.pk, "weight": 2}]
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            {"non_field_errors": ["This group has no votes."]}, response.json()
        )

    def test_set_vote_dist_not_potential_voter(self):
        self.meeting.remove_roles(self.hangaround, ROLE_POTENTIAL_VOTER)
        response = self._post(
            self.lead_hat,
            weights=[
                {"user": self.lead_hat.pk, "weight": 2},
                {"user": self.hangaround.pk, "weight": 2},
            ],
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            {
                "weights": [
                    f"The following user PKs aren't potential voters: {self.hangaround.pk}."
                ]
            },
            response.json(),
        )

    def test_set_vote_wrong_er(self):
        self.meeting.er_policy_name = None
        self.meeting.save()
        response = self._post(
            self.lead_hat, weights=[{"user": self.lead_hat.pk, "weight": 4}]
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            {
                "non_field_errors": [
                    "This message is only valid while using gv_auto_before_p electoral register policy."
                ]
            },
            response.json(),
        )

    def test_set_vote_regular_participant(self):
        response = self._post(
            self.hangaround, weights=[{"user": self.lead_hat.pk, "weight": 4}]
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            {"non_field_errors": ["You're not delegation leader or moderator."]},
            response.json(),
        )

    def test_set_vote_non_member(self):
        response = self._post(
            self.moderator,
            weights=[
                {"user": self.lead_hat.pk, "weight": 2},
                {"user": self.moderator.pk, "weight": 2},
            ],
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            {
                "weights": [
                    f"The following user PKs aren't members of that group: {self.moderator.pk}."
                ]
            },
            response.json(),
        )
