from collections import Counter

from django.test import TestCase
from django_fsm import TransitionNotAllowed

from voteit.messaging.errors import ValidationErrorMsg
from voteit.poll.exceptions import InvalidProposalCount


def wiki_example_ballots(method) -> Counter:
    # Test from python-vote-core, rewritten as A=1 etc
    count_and_ballot = [
        # IE: {"count": 3, "ballot": [["A"], ["C"], ["D"], ["B"]]}
        (3, {1: 4, 3: 3, 4: 2, 2: 1}),
        (9, {2: 4, 1: 3, 3: 2, 4: 1}),
        (8, {3: 4, 4: 3, 1: 2, 2: 1}),
        (5, {4: 4, 1: 3, 2: 2, 3: 1}),
        (5, {4: 4, 2: 3, 3: 2, 1: 1}),
    ]
    counter = Counter()
    schema = method.vote_schema
    for count, ballot in count_and_ballot:
        data = schema(ranking=ballot)
        key = method.vote_to_str(data)
        counter[key] = count
    return counter


class SchulzeTests(TestCase):
    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister

        self.er = ElectoralRegister.objects.create()
        self.poll = Poll.objects.create(
            electoral_register=self.er, method_name="schulze"
        )
        self.poll.upcoming()
        self.poll.save()

    @property
    def _cut(self):
        from voteit.poll.app.polls.schulze import Schulze

        return Schulze

    def test_registration(self):
        self.assertIsInstance(self.poll.method, self._cut)

    def test_start_check(self):
        self.poll.proposals.create()
        self.assertRaises(InvalidProposalCount, self.poll.method.start_check)
        self.poll.proposals.create()
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

    def test_calc_vote_core_wiki_example(self):
        # Test from python-vote-core, rewritten as A=1 etc
        # Generate data
        method = self.poll.method
        counter = wiki_example_ballots(method)
        res = method.calculate_result(counter)
        # Run tests
        self.assertEqual(res.approved, [3])
        self.assertEqual(res.denied, [1, 2, 4])
        self.assertEqual({1, 2, 3, 4}, res.candidates)
        self.assertEqual(
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
            res.pairs,
        )
        self.assertEqual(
            {
                (4, 2): 21,
                (3, 4): 20,
                (2, 3): 19,
                (4, 1): 18,
                (1, 3): 17,
                (1, 2): 16,
            },
            res.strong_pairs,
        )
        self.assertEqual(res.winner, 3)

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
            (1, {10: 3, 20: 2, 30: 2}),
            (1, {20: 3, 10: 2, 30: 1}),
        ]
        for count, ballot in count_and_ballot:
            data = schema(ranking=ballot)
            key = method.vote_to_str(data)
            counter[key] = count
        result = method.calculate_result(counter)
        # Run tests
        self.assertEqual(result.candidates, {10, 20, 30})
        self.assertEqual(
            {
                (10, 20): 1,
                (10, 30): 2,
                (20, 10): 1,
                (20, 30): 1,
                (30, 10): 0,
                (30, 20): 0,
            },
            result.pairs,
        )
        self.assertEqual(
            {
                (10, 30): 2,
                (20, 30): 1,
            },
            result.strong_pairs,
        )
        self.assertEqual(result.tied_winners, {10, 20})


class RepeatedSchulzeTests(TestCase):
    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister

        self.er = ElectoralRegister.objects.create()
        self.poll = Poll.objects.create(
            electoral_register=self.er, method_name="repeated_schulze"
        )
        self.poll.upcoming()
        self.poll.save()

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
        self.assertEqual({1, 2, 3, 4}, result.candidates)
        self.assertEqual(4, len(result.rounds))
        # First round winner is of course the same
        self.assertEqual(3, result.rounds[0].winner)
        # So 3 were not in the second round
        self.assertNotIn(3, result.rounds[1].candidates)
        self.assertEqual({1, 2, 4}, result.rounds[1].candidates)
        self.assertEqual(4, result.rounds[1].winner)
        # Etc
        self.assertEqual({1, 2}, result.rounds[2].candidates)
        self.assertEqual(1, result.rounds[2].winner)
        self.assertEqual({2}, result.rounds[3].candidates)
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
        self.assertEqual({1, 2, 3, 4}, result.candidates)
        self.assertEqual(2, len(result.rounds))
        # First round winner is of course the same
        self.assertEqual(3, result.rounds[0].winner)
        # So 3 were not in the second round
        self.assertNotIn(3, result.rounds[1].candidates)
        self.assertEqual({1, 2, 4}, result.rounds[1].candidates)
        self.assertEqual(4, result.rounds[1].winner)


class AddSchulzeVoteTests(TestCase):
    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister

        self.er = ElectoralRegister.objects.create()
        self.poll = Poll.objects.create(
            electoral_register=self.er, method_name="schulze"
        )
        self.prop1 = self.poll.proposals.create()
        self.prop2 = self.poll.proposals.create()
        self.prop3 = self.poll.proposals.create()
        self.voter = self.er.voters.create(username="voter")
        self.poll.upcoming()
        self.poll.save()

    @property
    def _cut(self):
        from voteit.poll.app.polls.schulze import AddSchulzeVote

        return AddSchulzeVote

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.poll.pk)
        kw.setdefault(
            "vote", {"ranking": {self.prop1.pk: 10, self.prop2.pk: 5, self.prop3.pk: 1}}
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
