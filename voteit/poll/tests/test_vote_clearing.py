from datetime import timedelta
from unittest.mock import patch

from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now
from rest_framework.test import APITestCase

from voteit.core.anonymise import anonymise_user
from voteit.core.testing import FakeCommit
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.messaging.channels import UserChannel
from voteit.organisation.models import Organisation
from voteit.poll.app.er_policies.auto_always import AutoAlways
from voteit.poll.exceptions import PollError
from voteit.poll.jobs import auto_clear_votes
from voteit.poll.messages import GenericVoteResponse
from voteit.poll.models import Poll
from voteit.poll.models import Vote

User = get_user_model()


class VoteClearingFixture:
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(title="Org", host="org.test")
        cls.user = User.objects.create(username="voter", organisation=cls.org)
        cls.meeting = cls.mk_meeting(cls.org)
        cls.poll = cls.mk_poll(cls.meeting)
        cls.vote = cls.poll.votes.create(user=cls.user, vote="yes")
        cls.finish(cls.meeting, cls.poll, days_ago=91)

    @classmethod
    def mk_meeting(cls, org):
        meeting = Meeting.objects.create(
            organisation=org, er_policy_name=AutoAlways.name, state="ongoing"
        )
        meeting.add_roles(cls.user, ROLE_PARTICIPANT, ROLE_POTENTIAL_VOTER)
        return meeting

    @staticmethod
    def mk_poll(meeting):
        ai = meeting.agenda_items.create(state="ongoing")
        poll = meeting.polls.create(agenda_item=ai, method_name="simple")
        poll.proposals.add(ai.proposals.create())
        poll.ongoing(force=True)
        poll.save()
        return poll

    @staticmethod
    def finish(meeting, poll, *, days_ago, poll_state="finished"):
        Poll.objects.filter(pk=poll.pk).update(state=poll_state)
        Meeting.objects.filter(pk=meeting.pk).update(
            state="closed", end_time=now() - timedelta(days=days_ago)
        )


class VoteQuerySetTests(VoteClearingFixture, TestCase):
    def test_clearable_after_retention(self):
        self.assertEqual([self.vote], list(Vote.objects.clearable()))

    def test_not_before_retention(self):
        self.finish(self.meeting, self.poll, days_ago=89)
        self.assertFalse(Vote.objects.clearable().exists())

    def test_respects_org_retention(self):
        Organisation.objects.filter(pk=self.org.pk).update(vote_retention_days=100)
        self.assertFalse(Vote.objects.clearable().exists())

    def test_reopened_meeting(self):
        Meeting.objects.filter(pk=self.meeting.pk).update(state="ongoing")
        self.assertFalse(Vote.objects.clearable().exists())

    def test_poll_states(self):
        for state in ("finished", "withheld", "no_result", "canceled"):
            with self.subTest(state=state):
                Poll.objects.filter(pk=self.poll.pk).update(state=state)
                self.assertTrue(Vote.objects.clearable().exists())
        for state in ("failed", "closed", "ongoing", "upcoming", "private"):
            with self.subTest(state=state):
                Poll.objects.filter(pk=self.poll.pk).update(state=state)
                self.assertFalse(Vote.objects.clearable().exists())

    def test_clear(self):
        abstained = self.mk_poll(self.meeting)
        abstained.votes.create(user=self.user, abstain=True)
        self.finish(self.meeting, abstained, days_ago=91)

        self.assertEqual(2, Vote.objects.clearable().clear())

        for vote in Vote.objects.all():
            self.assertTrue(vote.cleared)
            self.assertIsNone(vote.vote_data)
            self.assertFalse(vote.abstain)
            self.assertGreater(vote.changed, now() - timedelta(minutes=1))
        self.assertFalse(Vote.objects.clearable().exists())
        self.assertEqual(2, Vote.objects.cleared().count())

    def test_clear_leaves_no_vote_data_in_auditlog(self):
        Vote.objects.clearable().clear()
        for entry in LogEntry.objects.get_for_object(self.vote):
            for field in ("vote_data", "abstain"):
                if field in entry.changes_dict:
                    self.assertNotIn("yes", str(entry.changes_dict[field]))

    def test_save_refuses_empty_vote(self):
        poll = self.mk_poll(self.mk_meeting(self.org))
        with self.assertRaises(PollError):
            poll.votes.create(user=self.user)

    def test_finalize_refuses_cleared_votes(self):
        poll = self.mk_poll(self.mk_meeting(self.org))
        vote = poll.votes.create(user=self.user, vote="yes")
        Vote.objects.filter(pk=vote.pk).clear()
        with self.assertRaises(PollError):
            poll.finalize_vote_data()

    def test_meeting_vote_clearable_after(self):
        meeting = Meeting.objects.get(pk=self.meeting.pk)
        self.assertEqual(
            meeting.end_time + timedelta(days=90), meeting.vote_clearable_after
        )
        meeting.state = "ongoing"
        self.assertIsNone(meeting.vote_clearable_after)

    def test_anonymise_deletes_cleared_votes(self):
        Vote.objects.clearable().clear()
        anonymise_user(self.user)
        self.assertFalse(Vote.objects.filter(user=self.user).exists())


class AutoClearVotesTests(VoteClearingFixture, TestCase):
    def test_only_orgs_with_auto_clear(self):
        other_org = Organisation.objects.create(title="Other", host="other.test")
        other_user = User.objects.create(username="other", organisation=other_org)
        other_meeting = Meeting.objects.create(
            organisation=other_org, er_policy_name=AutoAlways.name, state="ongoing"
        )
        other_meeting.add_roles(other_user, ROLE_PARTICIPANT, ROLE_POTENTIAL_VOTER)
        other_poll = self.mk_poll(other_meeting)
        other_vote = other_poll.votes.create(user=other_user, vote="yes")
        self.finish(other_meeting, other_poll, days_ago=91)
        Organisation.objects.filter(pk=other_org.pk).update(auto_clear_votes=True)

        self.assertEqual(1, auto_clear_votes())

        other_vote.refresh_from_db()
        self.assertTrue(other_vote.cleared)
        self.vote.refresh_from_db()
        self.assertFalse(self.vote.cleared)


class ClearVotesViewTests(VoteClearingFixture, APITestCase):
    url = reverse("vote-clear")

    def setUp(self):
        self.client.force_login(self.user)

    def test_anonymous(self):
        self.client.logout()
        response = self.client.post(self.url, {})
        self.assertIn(response.status_code, (401, 403))

    @patch.object(UserChannel, "sync_publish")
    def test_clear_all(self, mock_publish):
        pending_meeting = self.mk_meeting(self.org)
        pending_poll = self.mk_poll(pending_meeting)
        pending_poll.votes.create(user=self.user, vote="no")
        self.finish(pending_meeting, pending_poll, days_ago=10)
        mock_publish.reset_mock()

        with FakeCommit():
            response = self.client.post(self.url, {}, format="json")

        self.assertEqual(200, response.status_code, response.data)
        self.assertEqual(1, response.data["cleared"])
        pending_meeting.refresh_from_db()
        self.assertEqual(
            [
                {
                    "meeting": pending_meeting.pk,
                    "clearable_after": pending_meeting.vote_clearable_after,
                    "votes": 1,
                }
            ],
            response.data["pending"],
        )
        self.vote.refresh_from_db()
        self.assertTrue(self.vote.cleared)
        messages = [
            call.args[0]
            for call in mock_publish.call_args_list
            if isinstance(call.args[0], GenericVoteResponse)
        ]
        self.assertEqual(1, len(messages))
        self.assertIsNone(messages[0].payload.vote)
        self.assertFalse(messages[0].payload.abstain)

    def test_clear_one_meeting(self):
        other_meeting = self.mk_meeting(self.org)
        other_poll = self.mk_poll(other_meeting)
        other_vote = other_poll.votes.create(user=self.user, vote="no")
        self.finish(other_meeting, other_poll, days_ago=91)

        response = self.client.post(
            self.url, {"meeting": other_meeting.pk}, format="json"
        )

        self.assertEqual(1, response.data["cleared"])
        other_vote.refresh_from_db()
        self.assertTrue(other_vote.cleared)
        self.vote.refresh_from_db()
        self.assertFalse(self.vote.cleared)

    def test_other_users_votes_untouched(self):
        other = User.objects.create(username="other", organisation=self.org)
        self.client.force_login(other)
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(0, response.data["cleared"])
        self.vote.refresh_from_db()
        self.assertFalse(self.vote.cleared)

    def test_idempotent(self):
        self.client.post(self.url, {}, format="json")
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(0, response.data["cleared"])
