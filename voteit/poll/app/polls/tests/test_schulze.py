from collections import Counter

from django.test import TestCase
from django.test import override_settings

from voteit.messaging.errors import ValidationErrorMsg
from voteit.poll.exceptions import InvalidProposalCount

_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


def wiki_example_ballots(method) -> Counter:
    # Test from python-vote-core, rewritten as A=1 etc
    count_and_ballot = [
        # IE: {"count": 3, "ballot": [["A"], ["C"], ["D"], ["B"]]}
        (3, ((1, 4), (3, 3), (4, 2), (2, 1))),
        (9, ((2, 4), (1, 3), (3, 2), (4, 1))),
        (8, ((3, 4), (4, 3), (1, 2), (2, 1))),
        (5, ((4, 4), (1, 3), (2, 2), (3, 1))),
        (5, ((4, 4), (2, 3), (3, 2), (1, 1))),
    ]
    counter = Counter()
    schema = method.vote_schema
    for count, ballot in count_and_ballot:
        data = schema(ranking=ballot)
        key = method.vote_to_str(data)
        counter[key] = count
    return counter


class SchulzeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister

        cls.er = ElectoralRegister.objects.create()
        cls.poll = Poll.objects.create(electoral_register=cls.er, method_name="schulze")
        cls.poll.upcoming()
        cls.poll.save()

    @property
    def _cut(self):
        from voteit.poll.app.polls.schulze import Schulze

        return Schulze

    def test_registration(self):
        self.assertIsInstance(self.poll.method, self._cut)

    def test_start_check_no_deny(self):
        self.poll.proposals.create()
        self.assertRaises(InvalidProposalCount, self.poll.method.start_check)
        self.poll.proposals.create()
        self.assertRaises(InvalidProposalCount, self.poll.method.start_check)
        self.poll.proposals.create()
        self.assertIsNone(self.poll.method.start_check())

    def test_start_check_with_deny(self):
        self.poll.proposals.create()
        self.poll.settings = {"deny_proposal": True}
        self.poll.save()
        self.assertRaises(InvalidProposalCount, self.poll.method.start_check)
        self.poll.proposals.create()
        self.assertIsNone(self.poll.method.start_check())

    def test_calculate_result(self):
        counter = Counter()
        counter["[[10, 1], [20, 2], [30, 3]]"] = 5
        counter["[[10, 2], [20, 2], [30, 1]]"] = 10
        method = self.poll.method
        result = method.calculate_result(counter)
        self.assertEqual(result.winner, 20)

    def test_calculate_result_deny_winning(self):
        self.poll.settings = {"deny_proposal": True}
        self.poll.save()
        counter = Counter()
        counter["[[10, 1], [0, 2], [30, 3]]"] = 5
        counter["[[10, 2], [0, 2], [30, 1]]"] = 10
        method = self.poll.method
        result = method.calculate_result(counter)
        self.assertEqual(result.winner, 0)
        self.assertEqual(result.denied, [10, 30])

    def test_calc_vote_core_wiki_example(self):
        # Test from python-vote-core, rewritten as A=1 etc
        # Generate data
        method = self.poll.method
        counter = wiki_example_ballots(method)
        res = method.calculate_result(counter)
        # Run tests
        self.assertEqual(res.approved, [3])
        self.assertEqual(res.denied, [1, 2, 4])
        self.assertSetEqual({1, 2, 3, 4}, set(res.candidates))
        self.assertDictEqual(
            {
                (1, 2): 16,
                (1, 3): 17,
                (1, 4): 12,
                (2, 1): 14,
                (2, 3): 19,
                (2, 4): 9,
                (3, 1): 13,
                (3, 2): 11,
                (3, 4): 20,
                (4, 1): 18,
                (4, 2): 21,
                (4, 3): 10,
            },
            dict(res.pairs),
        )
        self.assertDictEqual(
            {
                (4, 2): 21,
                (3, 4): 20,
                (2, 3): 19,
                (4, 1): 18,
                (1, 3): 17,
                (1, 2): 16,
            },
            dict(res.strong_pairs),
        )
        self.assertEqual(res.winner, 3)

    def test_result_wiki_example_storage_and_json(self):
        method = self.poll.method
        counter = wiki_example_ballots(method)
        res = method.calculate_result(counter)
        self.poll.result = res
        # Just to make sure nothing dies
        self.assertIsInstance(res.json(), str)

    def test_calc_former_tiebreaker_bug(self):
        # Test from python-vote-core, rewritten as A=1 etc
        # Generate data
        counter = Counter()
        method = self.poll.method
        schema = method.vote_schema
        # Example input was:
        # input = [
        #     {"count": 1, "ballot": [["A"], ["B", "C"]]},
        #     {"count": 1, "ballot": [["B"], ["A"], ["C"]]},
        # ]
        count_and_ballot = [
            # A = 10 etc
            (1, ((10, 3), (20, 2), (30, 2))),
            (1, ((20, 3), (10, 2), (30, 1))),
        ]
        for count, ballot in count_and_ballot:
            data = schema(ranking=ballot)
            key = method.vote_to_str(data)
            counter[key] = count
        result = method.calculate_result(counter)
        # Run tests
        self.assertSetEqual(set(result.candidates), {10, 20, 30})
        self.assertDictEqual(
            {
                (10, 20): 1,
                (10, 30): 2,
                (20, 10): 1,
                (20, 30): 1,
                (30, 10): 0,
                (30, 20): 0,
            },
            dict(result.pairs),
        )
        self.assertDictEqual(
            {
                (10, 30): 2,
                (20, 30): 1,
            },
            dict(result.strong_pairs),
        )
        self.assertSetEqual(set(result.tied_winners), {10, 20})


class RepeatedSchulzeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister

        cls.er = ElectoralRegister.objects.create()
        cls.poll = Poll.objects.create(
            electoral_register=cls.er, method_name="repeated_schulze"
        )
        cls.poll.upcoming()
        cls.poll.save()

    @property
    def _cut(self):
        from voteit.poll.app.polls.schulze import RepeatedSchulze

        return RepeatedSchulze

    def test_registration(self):
        self.assertIsInstance(self.poll.method, self._cut)

    def test_winners_validation(self):
        with self.assertRaises(ValueError):
            self.poll.settings = {"winners": 1}
        self.poll.settings = {"winners": 2}
        self.poll.settings = {"winners": None}

    def test_winners_and_proposal_count_validation(self):
        self.poll.proposals.create()
        self.assertRaises(InvalidProposalCount, self.poll.method.start_check)
        self.poll.proposals.create()
        self.assertRaises(InvalidProposalCount, self.poll.method.start_check)
        self.poll.proposals.create()
        self.assertIsNone(self.poll.method.start_check())
        self.poll.settings = {"winners": 3}
        self.assertRaises(InvalidProposalCount, self.poll.method.start_check)
        self.poll.settings = {"winners": 2}
        self.assertIsNone(self.poll.method.start_check())

    def test_direct_change_of_settings(self):
        with self.assertRaises(TypeError):
            self.poll.settings.winners = 2

    def test_calc_results(self):
        from collections import Counter

        counter = Counter()
        counter["[[10, 1], [20, 2], [30, 3]]"] = 1
        self.poll.settings = {"winners": 2}
        [self.poll.proposals.create() for x in range(3)]
        result = self.poll.method.calculate_result(counter)
        self.assertEqual(30, result.rounds[0].winner)
        self.assertEqual(20, result.rounds[1].winner)
        self.assertSetEqual({10, 20}, set(result.rounds[1].candidates))
        self.assertEqual({20, 30}, set(result.approved))
        self.assertEqual({10}, set(result.denied))

    def test_calc_results_several_rounds_with_deny(self):
        from collections import Counter

        counter = Counter()
        counter["[[10, 1], [20, 2], [0, 3], [30, 4]]"] = 1
        self.poll.settings = {"winners": 3, "deny_proposal": True}
        [self.poll.proposals.create() for x in range(3)]
        result = self.poll.method.calculate_result(counter)
        self.assertEqual(30, result.rounds[0].winner)
        self.assertEqual(0, result.rounds[1].winner)
        self.assertEqual(2, len(result.rounds), "3rd round wasn't skipped")
        self.assertSetEqual(
            {30}, set(result.approved), "Only one winner since deny won second round"
        )

    def test_calc_results_all_rounds_aborted_due_to_winning_deny(self):
        from collections import Counter

        counter = Counter()
        counter["[[10, 1], [20, 2], [30, 3], [0, 4]]"] = 1
        self.poll.settings = {"winners": None, "deny_proposal": True}
        [self.poll.proposals.create() for x in range(3)]
        result = self.poll.method.calculate_result(counter)
        self.assertEqual(1, len(result.rounds), "Second round should be skipped")
        self.assertEqual(0, result.rounds[0].winner)
        self.assertSetEqual(set(), set(result.approved), "No winners")

    def test_calc_vote_core_wiki_example_with_full_rounds(self):
        # Test from python-vote-core, rewritten as A=1 etc
        # Generate data
        method = self.poll.method
        counter = wiki_example_ballots(method)
        # We need to create proposals to cause the method to calculate as many times as there are proposals
        [self.poll.proposals.create() for x in range(4)]
        result = method.calculate_result(counter)
        # Run tests
        self.assertEqual(result.approved, [])  # They were sorted
        self.assertEqual(result.denied, [])
        self.assertSetEqual({1, 2, 3, 4}, set(result.candidates))
        self.assertEqual(4, len(result.rounds))
        # First round winner is of course the same
        self.assertEqual(3, result.rounds[0].winner)
        # So 3 were not in the second round
        self.assertNotIn(3, result.rounds[1].candidates)
        self.assertSetEqual({1, 2, 4}, set(result.rounds[1].candidates))
        self.assertEqual(4, result.rounds[1].winner)
        # Etc
        self.assertSetEqual({1, 2}, set(result.rounds[2].candidates))
        self.assertEqual(1, result.rounds[2].winner)
        self.assertSetEqual({2}, set(result.rounds[3].candidates))
        self.assertEqual(2, result.rounds[3].winner)

    def test_calc_vote_core_wiki_example_with_2_winners(self):
        # Test from python-vote-core, rewritten as A=1 etc
        # Generate data
        method = self.poll.method
        counter = wiki_example_ballots(method)
        # Only run 2 iterations
        self.poll.settings = {"winners": 2}
        result = method.calculate_result(counter)
        # Run tests
        self.assertEqual(result.approved, [3, 4])  # Elected
        self.assertEqual(result.denied, [1, 2])
        self.assertSetEqual({1, 2, 3, 4}, set(result.candidates))
        self.assertEqual(2, len(result.rounds))
        # First round winner is of course the same
        self.assertEqual(3, result.rounds[0].winner)
        # So 3 were not in the second round
        self.assertNotIn(3, result.rounds[1].candidates)
        self.assertSetEqual({1, 2, 4}, set(result.rounds[1].candidates))
        self.assertEqual(4, result.rounds[1].winner)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AddSchulzeVoteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister

        cls.er = ElectoralRegister.objects.create()
        cls.poll = Poll.objects.create(electoral_register=cls.er, method_name="schulze")
        cls.prop1 = cls.poll.proposals.create()
        cls.prop2 = cls.poll.proposals.create()
        cls.prop3 = cls.poll.proposals.create()
        cls.voter = cls.er.voters.create(username="voter")
        cls.poll.upcoming()
        cls.poll.save()

    @property
    def _cut(self):
        from voteit.poll.app.polls.schulze import AddSchulzeVote

        return AddSchulzeVote

    def _mk_one(self, **kw):
        kw.setdefault("poll", self.poll.pk)
        kw.setdefault(
            "vote",
            {"ranking": ((self.prop1.pk, 10), (self.prop2.pk, 5), (self.prop3.pk, 1))},
        )
        return self._cut({"user_pk": self.voter.pk, "consumer_name": "abc"}, **kw)

    def test_add_vote(self):
        from voteit.poll.app.polls.schulze import SchulzePollResult

        self.poll.ongoing()
        self.poll.save()
        self.assertFalse(self.poll.votes.filter(user=self.voter).exists())
        msg = self._mk_one()
        msg.run_job()
        self.assertTrue(self.poll.votes.filter(user=self.voter).exists())
        self.poll.close()
        self.assertIsInstance(self.poll.result, SchulzePollResult)
        self.assertEqual(self.prop1.pk, self.poll.result.winner)

    def test_add_vote_on_repeated(self):
        from voteit.poll.app.polls.schulze import RepeatedSchulzeResult
        from voteit.poll.app.polls.schulze import RepeatedSchulze

        self.poll.method_name = RepeatedSchulze.name
        self.poll.method = RepeatedSchulze(self.poll)  # Remove chached property
        self.poll.settings = {"winners": 2}
        self.poll.ongoing()
        self.poll.save()
        self.assertFalse(self.poll.votes.filter(user=self.voter).exists())
        msg = self._mk_one()
        msg.run_job()
        self.assertTrue(self.poll.votes.filter(user=self.voter).exists())
        self.poll.close()
        self.assertIsInstance(self.poll.result, RepeatedSchulzeResult)
        self.assertEqual({self.prop1.pk, self.prop2.pk}, set(self.poll.result.approved))

    def test_add_vote_invalid_proposal(self):
        self.poll.ongoing()
        self.poll.save()
        msg = self._mk_one()
        msg.data.vote.ranking.append((-1, 10))
        self.assertRaises(ValidationErrorMsg, msg.run_job)
