from django.test import TestCase

from voteit.core.messages.user import InvalidateUserCache
from voteit.messaging.bundle import FRAME_OVERHEAD
from voteit.messaging.bundle import _json_size
from voteit.messaging.bundle import bind_bundle_schema
from voteit.messaging.bundle import iter_bundles
from voteit.messaging.messages import AppStateBundle
from voteit.messaging.registry import batch_for
from voteit.messaging.state import StateSection
from voteit.proposal.messages import ProposalChanged


def section(name, messages, failed=False):
    result = StateSection(name, failed=failed)
    result.messages = list(messages)
    return result


def bundles(sections, budget=None):
    return list(iter_bundles(sections, pk=1, channel_type="meeting", budget=budget))


def flatten(result):
    """(bundle seq, section name, complete, message count) for every section."""
    return [
        (bundle.payload.seq, s.name, s.complete, len(s.messages))
        for bundle in result
        for s in bundle.payload.sections
    ]


class IterBundlesTests(TestCase):
    def _messages(self, count):
        return [InvalidateUserCache(payload={"pk": i}) for i in range(count)]

    def test_everything_in_one_bundle(self):
        result = bundles([section("a", self._messages(5))])
        self.assertEqual(1, len(result))
        self.assertEqual([(0, "a", True, 5)], flatten(result))

    def test_several_collectors_share_a_bundle(self):
        result = bundles(
            [section("a", self._messages(2)), section("b", self._messages(2))]
        )
        self.assertEqual(1, len(result))
        self.assertEqual([(0, "a", True, 2), (0, "b", True, 2)], flatten(result))

    def test_empty_section_still_reported_complete(self):
        """The client was told to expect it, so it has to be told it is done."""
        result = bundles([section("a", [])])
        self.assertEqual([(0, "a", True, 0)], flatten(result))

    def test_no_sections_produces_nothing(self):
        self.assertEqual([], bundles([]))

    def test_failed_flag_survives(self):
        result = bundles([section("a", self._messages(1), failed=True)])
        self.assertTrue(result[0].payload.sections[0].failed)

    def test_pk_and_channel_type_on_every_frame(self):
        result = bundles([section("a", self._messages(6))], budget=FRAME_OVERHEAD + 120)
        self.assertGreater(len(result), 1)
        for bundle in result:
            self.assertEqual(1, bundle.payload.pk)
            self.assertEqual("meeting", bundle.payload.channel_type)

    def test_seq_counts_up(self):
        result = bundles([section("a", self._messages(4))], budget=FRAME_OVERHEAD + 120)
        self.assertEqual(list(range(len(result))), [b.payload.seq for b in result])

    def test_oversized_section_spills_and_only_the_last_is_complete(self):
        result = bundles([section("a", self._messages(3))], budget=FRAME_OVERHEAD + 120)
        self.assertEqual(
            [(0, "a", False, 1), (1, "a", False, 1), (2, "a", True, 1)],
            flatten(result),
        )

    def test_bundles_stay_within_budget(self):
        budget = FRAME_OVERHEAD + 400
        result = bundles(
            [section("a", self._messages(20)), section("b", self._messages(20))],
            budget=budget,
        )
        self.assertGreater(len(result), 1)
        for bundle in result:
            self.assertLessEqual(_json_size(bundle), budget)

    def test_no_message_is_lost(self):
        result = bundles(
            [section("a", self._messages(9)), section("b", self._messages(9))],
            budget=FRAME_OVERHEAD + 200,
        )
        pks = [
            m.payload.pk
            for bundle in result
            for s in bundle.payload.sections
            for m in s.messages
        ]
        self.assertEqual(list(range(9)) * 2, pks)


class SplitBatchTests(TestCase):
    def _batch(self, count):
        batch_cls = batch_for(ProposalChanged)
        return batch_cls(payload={"items": [{"pk": i} for i in range(count)]})

    def test_oversized_batch_is_rechunked(self):
        result = bundles([section("a", [self._batch(30)])], budget=FRAME_OVERHEAD + 300)
        messages = [m for b in result for s in b.payload.sections for m in s.messages]
        self.assertGreater(len(messages), 1)
        for message in messages:
            self.assertEqual("proposal.changed.batch", message.action)
        # Every item survives, in order, spread over the smaller batches.
        pks = [item.pk for message in messages for item in message.payload.items]
        self.assertEqual(list(range(30)), pks)

    def test_single_oversized_message_goes_out_alone(self):
        """Nothing can be split; it is sent anyway rather than dropped."""
        big = ProposalChanged(payload={"pk": 1, "body": "x" * 5000})
        result = bundles([section("a", [big])], budget=FRAME_OVERHEAD + 100)
        self.assertEqual([(0, "a", True, 1)], flatten(result))


class BundleSchemaTests(TestCase):
    def test_payload_union_is_bound(self):
        """The nested messages validate as their real types, not as BaseMessage.

        bind_bundle_schema() retargets a field annotation after the fact, which
        is the one part of this that pydantic does not formally promise. If it
        ever stops working, this is what says so.
        """
        bind_bundle_schema()
        original = bundles([section("a", [ProposalChanged(payload={"pk": 7})])])[0]
        restored = AppStateBundle.model_validate(original.model_dump(mode="json"))
        message = restored.payload.sections[0].messages[0]
        self.assertIsInstance(message, ProposalChanged)
        self.assertEqual(7, message.payload.pk)

    def test_schema_documents_the_union(self):
        bind_bundle_schema()
        schema = AppStateBundle.model_json_schema()
        self.assertIn("discriminator", str(schema))
        self.assertIn("proposal.changed", str(schema))
