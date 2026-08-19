from django.test import TestCase
from django.test import override_settings

from voteit.agenda.messages import AgendaChanged
from voteit.messaging.batch import make_batch
from voteit.messaging.registry import action_of
from voteit.messaging.registry import batch_for
from voteit.messaging.utils import Target
from voteit.messaging.utils import TransactionBatcher


class MakeBatchTests(TestCase):
    def test_action_is_suffixed(self):
        self.assertEqual(
            "agenda_item.changed.batch", action_of(batch_for(AgendaChanged))
        )

    def test_registered_by_the_outgoing_decorator(self):
        # @outgoing generates the sibling, so it is the same class object every
        # time rather than a fresh one per call.
        self.assertIs(batch_for(AgendaChanged), batch_for(AgendaChanged))

    def test_back_reference_to_source(self):
        self.assertIs(batch_for(AgendaChanged).batched_type, AgendaChanged)

    def test_payload_items_are_typed(self):
        batch = batch_for(AgendaChanged)(payload={"items": [{"pk": 1}, {"pk": 2}]})
        self.assertEqual([1, 2], [x.pk for x in batch.payload.items])

    def test_extra_keys_survive(self):
        # Payloads carry whatever the serializer produced; extra="allow" has to
        # hold through the batch wrapper too.
        batch = batch_for(AgendaChanged)(payload={"items": [{"pk": 1, "title": "Hi"}]})
        self.assertEqual({"title": "Hi"}, batch.payload.items[0].model_extra)

    def test_dump_shape(self):
        batch = batch_for(AgendaChanged)(payload={"items": [{"pk": 1}]})
        self.assertEqual(
            {"action": "agenda_item.changed.batch", "payload": {"items": [{"pk": 1}]}},
            batch.model_dump(mode="json"),
        )

    def test_payloadless_message_cannot_be_batched(self):
        from typing import Literal

        from chanx.messages.base import BaseMessage

        class NoPayload(BaseMessage):
            action: Literal["test.no_payload"] = "test.no_payload"
            payload: None = None

        with self.assertRaises(TypeError):
            make_batch(NoPayload)


@override_settings(VOTEIT_BATCH_THRESHOLD=3)
class TransactionBatcherTests(TestCase):
    target = Target("meeting_1")
    other = Target("meeting_2")

    def _collapse(self, pairs):
        batcher = TransactionBatcher()
        for message, target in pairs:
            batcher.add(message, target)
        return batcher.collapse()

    def _msg(self, pk):
        return AgendaChanged(payload={"pk": pk})

    def test_collapses_at_threshold(self):
        out = self._collapse([(self._msg(i), self.target) for i in range(3)])
        self.assertEqual(1, len(out))
        self.assertEqual("agenda_item.changed.batch", out[0][0].action)
        self.assertEqual([0, 1, 2], [x.pk for x in out[0][0].payload.items])

    def test_leaves_below_threshold_alone(self):
        out = self._collapse([(self._msg(i), self.target) for i in range(2)])
        self.assertEqual(
            ["agenda_item.changed", "agenda_item.changed"], [m.action for m, _ in out]
        )

    def test_never_merges_across_targets(self):
        out = self._collapse(
            [(self._msg(i), self.target) for i in range(3)]
            + [(self._msg(i), self.other) for i in range(3)]
        )
        self.assertEqual(2, len(out))
        self.assertEqual([self.target, self.other], [t for _, t in out])

    def test_preserves_order_across_groups(self):
        # Ordering matters: a poll referring to proposals must not overtake the
        # proposals themselves.
        from voteit.poll.messages import PollChanged

        out = self._collapse(
            [(self._msg(i), self.target) for i in range(3)]
            + [(PollChanged(payload={"pk": 9}), self.target)]
        )
        self.assertEqual(
            ["agenda_item.changed.batch", "poll.changed"], [m.action for m, _ in out]
        )

    def test_empty(self):
        self.assertEqual([], self._collapse([]))
