from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from pydantic import ValidationError

from envelope.messages.errors import BadRequestError
from envelope.messages.errors import UnauthorizedError
from envelope.messages.errors import ValidationErrorMsg

from voteit.meeting.models import Meeting
from voteit.poll.app.er_policies.auto_before_poll import AutoBeforePoll
from voteit.poll.app.er_policies.manual import Manual
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll

_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


User = get_user_model()


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AddVoteTests(TestCase):
    """Since this is an abstract class, we'll use simple vote to test it"""

    @classmethod
    def setUpTestData(cls):
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.voter = cls.er.voters.create(username="voter")
        cls.poll: Poll = Poll.objects.create(
            electoral_register=cls.er, method_name="simple"
        )
        cls.poll.proposals.create()
        cls.poll.upcoming()
        cls.poll.save()

    def setUp(self):
        self.poll.refresh_from_db()

    @property
    def _cut(self):
        from voteit.poll.app.polls.simple import AddSimpleVote

        return AddSimpleVote

    def _mk_one(self, **kw):
        kw.setdefault("vote", {"choice": "yes"})
        kw.setdefault("poll", self.poll.pk)
        return self._cut(mm={"user_pk": self.voter.pk, "consumer_name": "abc"}, **kw)

    def test_add(self):
        self.poll.ongoing()
        self.poll.save()
        msg = self._mk_one()
        msg.run_job()
        vote = self.poll.votes.filter(user=self.voter).first()
        self.assertIsNotNone(vote)
        self.assertEqual("yes", vote.vote_data)

    def test_add_not_started(self):
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_add_closed_poll(self):
        self.poll.ongoing()
        self.poll.close()
        self.poll.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_add_vote_exists(self):
        self.poll.ongoing()
        self.poll.save()
        self.vote = self.poll.votes.create(user=self.voter, vote_data="no")
        msg = self._mk_one()
        response = msg.run_job()
        vote = self.poll.votes.filter(user=self.voter).first()
        self.assertEqual("yes", vote.vote_data)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AbstainTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.voter = cls.er.voters.create(username="voter")
        cls.poll: Poll = Poll.objects.create(
            electoral_register=cls.er, method_name="simple"
        )
        cls.poll.proposals.create()
        cls.poll.upcoming()
        cls.poll.ongoing()
        cls.poll.save()

    def setUp(self):
        self.poll.refresh_from_db()

    @property
    def _cut(self):
        from voteit.poll.messages import AbstainVote

        return AbstainVote

    def _mk_one(self, **kw):
        kw.setdefault("poll", self.poll.pk)
        return self._cut(mm={"user_pk": self.voter.pk, "consumer_name": "abc"}, **kw)

    def test_abstain(self):
        msg = self._mk_one()
        msg.run_job()
        vote = self.poll.votes.filter(user=self.voter).first()
        self.assertIsNotNone(vote)
        self.assertIs(vote.vote_data, None)
        self.assertIs(vote.abstain, True)

    def test_abstain_existing(self):
        from voteit.poll.app.polls.simple import AddSimpleVote

        AddSimpleVote(
            mm={"user_pk": self.voter.pk, "consumer_name": "abc"},
            vote={"choice": "yes"},
            poll=self.poll.pk,
        ).run_job()
        self.test_abstain()


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ChangeVoteTests(TestCase):
    """Since this is an abstract class, we'll use simple vote to test it"""

    @classmethod
    def setUpTestData(cls):
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.voter = cls.er.voters.create(username="voter")
        cls.poll: Poll = Poll.objects.create(
            electoral_register=cls.er, method_name="simple"
        )
        cls.poll.proposals.create()
        cls.poll.upcoming()
        cls.poll.ongoing()
        cls.poll.save()
        cls.vote = cls.poll.votes.create(user=cls.voter, vote_data="yes")

    @property
    def _cut(self):
        from voteit.poll.app.polls.simple import AddSimpleVote

        return AddSimpleVote

    def _mk_one(self, **kw):
        kw.setdefault("vote", {"choice": "no"})
        kw.setdefault("poll", self.poll.pk)
        return self._cut(mm={"user_pk": self.voter.pk, "consumer_name": "abc"}, **kw)

    def test_change(self):
        msg = self._mk_one()
        msg.run_job()
        self.vote.refresh_from_db()
        self.assertEqual("no", self.vote.vote_data)

    def test_change_closed(self):
        self.poll.close()
        self.poll.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ManualCreateERTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.meeting.er_policy_name = Manual.name
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.meeting.add_roles(cls.participant, "potential_voter")

    def setUp(self):
        self.meeting.refresh_from_db()

    @property
    def _cut(self):
        from voteit.poll.messages import ManualCreateER

        return ManualCreateER

    def _mk_one(self, user, **kw):
        kw.setdefault("meeting", self.meeting.pk)
        kw.setdefault("weights", [{"user": self.participant.pk, "weight": 1}])
        return self._cut(
            mm={"user_pk": user.pk, "consumer_name": "abc", "id": "1"}, **kw
        )

    def test_add_moderator(self):
        msg = self._mk_one(self.moderator)
        response = msg.run_job()
        self.assertEqual(1, self.meeting.electoral_registers.count())
        self.assertEqual(
            ["participant"],
            list(self.meeting.latest_er.voters.values_list("username", flat=True)),
        )
        self.assertEqual("1", response.mm.id)

    def test_add_participant(self):
        msg = self._mk_one(self.participant)
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_add_not_needed(self):
        msg = self._mk_one(self.moderator)
        msg.run_job()
        self.assertEqual(1, self.meeting.electoral_registers.count())
        msg.run_job()
        self.assertEqual(1, self.meeting.electoral_registers.count())

    def test_add_with_weight(self):
        msg = self._mk_one(
            self.moderator, weights=[{"user": self.participant.pk, "weight": 5}]
        )
        msg.run_job()
        self.assertEqual({2: 5}, self.meeting.latest_er.weight_dict)

    def test_add_with_weight_bad_user(self):
        msg = self._mk_one(self.moderator, weights=[{"user": 0, "weight": 1}])
        self.assertRaises(ValidationErrorMsg, msg.run_job)

    def test_add_without_specification(self):
        msg = self._mk_one(self.moderator)
        msg.run_job()
        self.assertEqual({2: 1}, self.meeting.latest_er.weight_dict)

    def test_add_with_duplicate(self):
        msg = self._mk_one(
            self.moderator,
            weights=[
                {"user": self.participant.pk, "weight": 5},
                {"user": self.participant.pk, "weight": 3},
            ],
        )
        self.assertRaises(ValidationError, msg.run_job)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class TriggerCreateERTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.meeting.er_policy_name = AutoBeforePoll.name
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.meeting.add_roles(cls.participant, "potential_voter")

    @property
    def _cut(self):
        from voteit.poll.messages import TriggerCreateER

        return TriggerCreateER

    def _mk_one(self, user, **kw):
        kw.setdefault("meeting", self.meeting.pk)
        return self._cut(
            mm={"user_pk": user.pk, "consumer_name": "abc", "id": "1"}, **kw
        )

    def test_actor_moderator(self):
        msg = self._mk_one(self.moderator)
        response = msg.run_job()
        self.assertEqual(1, self.meeting.electoral_registers.count())
        self.assertEqual(
            ["participant"],
            list(self.meeting.latest_er.voters.values_list("username", flat=True)),
        )
        self.assertEqual("1", response.mm.id)

    def test_actor_participant(self):
        msg = self._mk_one(self.participant)
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_no_valid_policy(self):
        self.meeting.er_policy_name = None
        self.meeting.save()
        msg = self._mk_one(self.moderator)
        with self.assertRaises(BadRequestError) as cm:
            msg.run_job()
        self.assertIn("No valid electoral registry", str(cm.exception.data.msg))

    def test_trigger_not_allowed(self):
        self.meeting.er_policy_name = Manual.name
        self.meeting.save()
        msg = self._mk_one(self.moderator)
        with self.assertRaises(BadRequestError) as cm:
            msg.run_job()
        self.assertIn(
            "Electoral register can't be triggered this way", str(cm.exception.data.msg)
        )
