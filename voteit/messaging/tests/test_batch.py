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

    def test_groups_go_out_in_order_of_first_occurrence(self):
        from voteit.poll.messages import PollChanged

        out = self._collapse(
            [(self._msg(i), self.target) for i in range(3)]
            + [(PollChanged(payload={"pk": 9}), self.target)]
        )
        self.assertEqual(
            ["agenda_item.changed.batch", "poll.changed"], [m.action for m, _ in out]
        )

    def test_a_later_message_joins_its_earlier_group(self):
        # The limit of the ordering guarantee, pinned rather than endorsed: a
        # second poll added last leaves with the first one, ahead of the
        # agenda items it was queued behind. See the TransactionBatcher
        # docstring.
        from voteit.poll.messages import PollChanged

        out = self._collapse(
            [(PollChanged(payload={"pk": 8}), self.target)]
            + [(self._msg(i), self.target) for i in range(3)]
            + [(PollChanged(payload={"pk": 9}), self.target)]
        )
        self.assertEqual(
            ["poll.changed", "poll.changed", "agenda_item.changed.batch"],
            [m.action for m, _ in out],
        )
        self.assertEqual([8, 9], [m.payload.pk for m, _ in out[:2]])

    def test_empty(self):
        self.assertEqual([], self._collapse([]))

    def test_already_batched_messages_are_passed_through(self):
        # A publisher may hand sync_publish a pre-built <action>.batch -- see
        # voteit.speaker.signals.notify_active_list_changed. A batch has no
        # batch sibling of its own, so trying to collapse a run of them used to
        # raise LookupError from inside the on_commit hook, after the write had
        # already been committed.
        batch = batch_for(AgendaChanged)
        out = self._collapse(
            [(batch(payload={"items": [{"pk": i}]}), self.target) for i in range(3)]
        )
        self.assertEqual(["agenda_item.changed.batch"] * 3, [m.action for m, _ in out])

    def test_unregistered_messages_are_passed_through(self):
        # Same reasoning: never raise from the commit hook.
        from typing import Literal

        from chanx.messages.base import BaseMessage
        from pydantic import BaseModel

        class Payload(BaseModel):
            pk: int

        class Unregistered(BaseMessage):
            action: Literal["test.unregistered"] = "test.unregistered"
            payload: Payload

        out = self._collapse(
            [(Unregistered(payload={"pk": i}), self.target) for i in range(3)]
        )
        self.assertEqual(["test.unregistered"] * 3, [m.action for m, _ in out])
