from __future__ import annotations

from django.test import TestCase
from django.test import override_settings

from voteit.core.messages.user import InvalidateUserCache
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.channels import broadcast_meeting
from voteit.meeting.models import Meeting
from voteit.messaging.registry import collectors_for
from voteit.messaging.registry import context_channel_registry
from voteit.messaging.testing import MessageCatcher
from voteit.messaging.testing import testing_channel_layers_setting
from voteit.organisation.models import Organisation


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class BroadcastMeetingTests(TestCase):
    """The replacement for the old ``meeting`` channel.

    That channel had the same permission as ``participants``, so it never
    reached anyone these two do not -- it only cost the client a second
    subscribe and a second app state snapshot.
    """

    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create(title="Org", host="testserver")
        cls.meeting = Meeting.objects.create(
            title="Meeting", organisation=cls.organisation
        )

    def _broadcast(self, meeting):
        # __enter__ hands back the message list, so keep the catcher itself --
        # it is the only thing that knows which target each message went to.
        catcher = MessageCatcher(InvalidateUserCache)
        with catcher:
            broadcast_meeting(
                meeting, InvalidateUserCache(payload={"pk": 1}), on_commit=False
            )
        return catcher

    def test_reaches_both_groups(self):
        messages = self._broadcast(self.meeting)
        self.assertEqual(2, len(messages))
        self.assertEqual(
            [
                f"participants_{self.meeting.pk}",
                f"moderators_{self.meeting.pk}",
            ],
            [t.name for t in messages.targets],
        )
        self.assertTrue(all(t.group for t in messages.targets))

    def test_accepts_a_bare_pk(self):
        """Callers pass whichever they already hold; only the pk is read."""
        by_pk = self._broadcast(self.meeting.pk)
        self.assertEqual(
            [f"participants_{self.meeting.pk}", f"moderators_{self.meeting.pk}"],
            [t.name for t in by_pk.targets],
        )

    def test_no_query_for_either_form(self):
        """Publishing never touches ``context``, so neither form hits the db."""
        with self.assertNumQueries(0):
            self._broadcast(self.meeting.pk)
            self._broadcast(self.meeting)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class BroadcastBatchingTests(TestCase):
    """Batching survives the split -- it just collapses once per group."""

    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create(title="Org", host="testserver")
        cls.meeting = Meeting.objects.create(
            title="Meeting", organisation=cls.organisation
        )

    @override_settings(VOTEIT_BATCH_THRESHOLD=3)
    def test_collapses_per_group(self):
        catcher = MessageCatcher()
        with catcher:
            with self.captureOnCommitCallbacks(execute=True):
                for pk in range(3):
                    broadcast_meeting(
                        self.meeting, InvalidateUserCache(payload={"pk": pk})
                    )
        messages = catcher
        self.assertEqual(
            ["user.inv.batch", "user.inv.batch"],
            [m.action for m in messages],
        )
        self.assertEqual(
            [f"participants_{self.meeting.pk}", f"moderators_{self.meeting.pk}"],
            [t.name for t in catcher.targets],
        )
        for message in messages:
            self.assertEqual([0, 1, 2], [item.pk for item in message.payload.items])


class MeetingChannelRemovedTests(TestCase):
    """``meeting`` is gone from the wire, not merely unused."""

    def test_not_subscribable(self):
        self.assertNotIn("meeting", context_channel_registry)

    def test_both_channels_collect_the_same_sections(self):
        """A subscriber gets one stream now, whichever side they are on.

        The two differ only in what three of them return -- agenda.items,
        poll.polls and proposal.proposals branch on the channel -- never in
        which collectors run.
        """
        participants = [c.name for c in collectors_for(ParticipantsChannel)]
        moderators = [c.name for c in collectors_for(ModeratorsChannel)]
        self.assertEqual(participants, moderators)
        for name in ("meeting.roles", "room.rooms", "poll.own_votes", "agenda.items"):
            self.assertIn(name, participants)

    def test_collectors_are_ordered(self):
        for channel in (ParticipantsChannel, ModeratorsChannel):
            with self.subTest(channel=channel.name):
                found = collectors_for(channel)
                self.assertEqual(sorted(found, key=lambda c: (c.order, c.name)), found)
