from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from voteit.agenda.channels import AgendaItemChannel
from voteit.meeting.channels import MeetingChannel
from voteit.messaging.channels.user import UserChannel
from voteit.messaging.messages.channels import Subscribed, Subscribe

User = get_user_model()


_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SignalButtonTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.prop = self.ai.proposals.create()
        self.disc = self.ai.discussions.create()
        self.button = self.meeting.reactionbutton_set.create()
        self.moderator = User.objects.create(username="moderator")
        self.meeting.add_roles(self.moderator, "moderator")

    @patch.object(MeetingChannel, "publish")
    def test_button_added(self, mock_publish):
        from voteit.reactions.messages import ButtonAdded

        button = self.meeting.reactionbutton_set.create()

        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ButtonAdded)
        self.assertEqual(button.pk, msg.data.pk)

    @patch.object(MeetingChannel, "publish")
    def test_button_changed(self, mock_publish):
        from voteit.reactions.messages import ButtonChanged

        self.assertFalse(mock_publish.called)
        self.button.title = "I'm new"
        self.button.save()
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ButtonChanged)
        self.assertEqual(self.button.pk, msg.data.pk)
        self.assertEqual(self.button.title, "I'm new")

    @patch.object(MeetingChannel, "publish")
    def test_button_deleted(self, mock_publish):
        from voteit.reactions.messages import ButtonDeleted

        self.assertFalse(mock_publish.called)
        button_pk = self.button.pk
        self.button.delete()

        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ButtonDeleted)
        self.assertEqual(button_pk, msg.data.pk)

    def test_meeting_channel_subscribed(self):
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.moderator.pk},
            pk=self.meeting.pk,
            channel_type="meeting",
        )
        msg = command.run_job()
        unpacked = dict([(x.t, x.p) for x in msg.data.app_state])
        self.assertIn("reaction_button.added", unpacked)
        self.assertEqual(self.button.pk, unpacked["reaction_button.added"]["pk"])

    def test_ai_channel_subscribed(self):
        other = User.objects.create(username="other")
        self.prop.reaction_set.create(
            user=self.moderator, button=self.button, agenda_item=self.ai
        )
        self.prop.reaction_set.create(
            user=other, button=self.button, agenda_item=self.ai
        )
        self.disc.reaction_set.create(
            user=self.moderator, button=self.button, agenda_item=self.ai
        )
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.moderator.pk},
            pk=self.ai.pk,
            channel_type="agenda_item",
        )
        msg = command.run_job()
        reactions = [x for x in msg.data.app_state if x.t == "reaction.added"]
        self.assertEqual(2, len(reactions))
        self.assertEqual(self.button.pk, reactions[0].p["button"])
        counts = [m for m in msg.data.app_state if m.t == "reaction.count"]
        self.assertEqual(len(counts), 2)
        self.assertEqual(sum(c.p["count"] for c in counts), 3)


class SignalReactionTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.prop = self.ai.proposals.create()
        self.button = self.meeting.reactionbutton_set.create()
        self.user = User.objects.create(username="hej")

    def _mk_reaction(self, **kw):
        from voteit.reactions.models import Reaction

        kw.setdefault("object", self.prop)
        kw.setdefault("button", self.button)
        kw.setdefault("user", self.user)
        kw.setdefault("agenda_item", self.ai)
        return Reaction.objects.create(**kw)

    @patch.object(AgendaItemChannel, "publish")
    def test_reaction_added_ai(self, mock_publish):
        from voteit.reactions.messages import ReactionCount

        self.assertFalse(mock_publish.called)
        reaction = self._mk_reaction()
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ReactionCount)
        self.assertEqual(1, msg.data.count)
        self.assertEqual(self.button.pk, msg.data.button)
        self.assertEqual(self.prop.pk, msg.data.object_id)
        self.assertEqual("proposal.proposal", msg.data.content_type)

    @patch.object(AgendaItemChannel, "publish")
    def test_reaction_deleted_ai(self, mock_publish):
        from voteit.reactions.messages import ReactionCount

        self.assertFalse(mock_publish.called)
        reaction = self._mk_reaction()
        reaction.delete()
        msg = mock_publish.mock_calls[-1].args[0]
        self.assertIsInstance(msg, ReactionCount)
        self.assertEqual(0, msg.data.count)
        self.assertEqual(self.button.pk, msg.data.button)
        self.assertEqual(self.prop.pk, msg.data.object_id)
        self.assertEqual("proposal.proposal", msg.data.content_type)

    @patch.object(UserChannel, "publish")
    def test_reaction_added_user(self, mock_publish):
        from voteit.reactions.messages import UserReactionAdded

        self.assertFalse(mock_publish.called)
        reaction = self._mk_reaction()
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, UserReactionAdded)
        self.assertEqual(reaction.pk, msg.data.pk)
        self.assertEqual(self.button.pk, msg.data.button)
        self.assertEqual(self.prop.pk, msg.data.object_id)
        self.assertEqual("proposal.proposal", msg.data.content_type)

    @patch.object(UserChannel, "publish")
    def test_reaction_deleted_user(self, mock_publish):
        from voteit.reactions.messages import UserReactionDeleted

        self.assertFalse(mock_publish.called)
        reaction = self._mk_reaction()
        reaction_pk = reaction.pk
        reaction.delete()
        msg = mock_publish.mock_calls[-1].args[0]
        self.assertIsInstance(msg, UserReactionDeleted)
        self.assertEqual(reaction_pk, msg.data.pk)
