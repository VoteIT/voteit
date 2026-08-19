from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase
from django.test import override_settings
from envelope.app.user_channel.channel import UserChannel
from envelope.channels.messages import Subscribe
from envelope.channels.messages import Subscribed
from envelope.channels.models import AppState
from envelope.testing import MessageCatcher

from voteit.agenda.channels import AgendaItemChannel
from voteit.discussion.models import DiscussionPost
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.proposal.models import DiffProposal
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument
from voteit.reactions.models import Reaction
from voteit.reactions.models import ReactionButton

User = get_user_model()


_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SignalButtonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop = cls.ai.proposals.create()
        cls.disc = cls.ai.discussions.create()
        cls.button = cls.meeting.reaction_buttons.create()
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)

    @patch.object(MeetingChannel, "sync_publish")
    def test_button_added(self, mock_publish):
        from voteit.reactions.messages import ButtonChanged

        button = self.meeting.reaction_buttons.create(title="Btn")
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ButtonChanged)
        self.assertEqual(button.pk, msg.data.pk)

    @patch.object(MeetingChannel, "sync_publish")
    def test_button_changed(self, mock_publish):
        from voteit.reactions.messages import ButtonChanged

        self.assertFalse(mock_publish.called)
        self.button.title = "I'm new"
        self.button.save()
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ButtonChanged)
        self.assertEqual(self.button.pk, msg.data.pk)
        self.assertEqual(self.button.title, "I'm new")

    @patch.object(MeetingChannel, "sync_publish")
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
            mm={"consumer_name": "abc", "user_pk": self.moderator.pk},
            pk=self.meeting.pk,
            channel_type="meeting",
        )
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertIsInstance(msg, Subscribed)
        unpacked = {x.t: x.p for x in msg.data.app_state}
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
            mm={"consumer_name": "abc", "user_pk": self.moderator.pk},
            pk=self.ai.pk,
            channel_type="agenda_item",
        )
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertIsInstance(msg, Subscribed)
        batched_payload = [
            x.p["payloads"]
            for x in msg.data.app_state
            if x.t == "s.batch" and x.p.get("t") == "reaction.added"
        ]
        self.assertEqual(1, len(batched_payload))
        payloads = batched_payload[0]
        self.assertEqual(2, len(payloads))
        self.assertEqual(self.button.pk, payloads[0].button)
        counts = [m for m in msg.data.app_state if m.t == "reaction.count"]
        self.assertEqual(len(counts), 2)
        self.assertEqual(sum(c.p["count"] for c in counts), 3)

    def test_ai_channel_subscribed_n1_problem(self):
        from voteit.reactions.signals import ai_channel_subscribed

        button2: ReactionButton = self.meeting.reaction_buttons.create(title="2")
        button3 = self.meeting.reaction_buttons.create(title="3")
        flag1 = self.meeting.reaction_buttons.create(flag_mode=True, title="f1")
        flag2 = self.meeting.reaction_buttons.create(flag_mode=True, title="f2")
        flag3 = self.meeting.reaction_buttons.create(flag_mode=True, title="f3")
        for btn in (self.button, button2, button3, flag1, flag2, flag3):
            btn.reactions.create(object=self.prop, user=self.moderator)
            btn.reactions.create(object=self.disc, user=self.moderator)
        app_state = AppState()
        with self.assertNumQueries(2):
            ai_channel_subscribed(self.ai, app_state, self.moderator)


class SignalReactionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop = cls.ai.proposals.create()
        cls.button = cls.meeting.reaction_buttons.create()
        cls.user = User.objects.create(username="hej")
        cls.text_doc: TextDocument = TextDocument.objects.create(
            body="Hello", base_tag="hi"
        )
        cls.para = cls.text_doc.text_paragraphs.first()
        cls.disc = cls.ai.discussions.create()

    def _mk_reaction(self, **kw):
        kw.setdefault("object", self.prop)
        kw.setdefault("button", self.button)
        kw.setdefault("user", self.user)
        kw.setdefault("agenda_item", self.ai)
        return Reaction.objects.create(**kw)

    @patch.object(AgendaItemChannel, "sync_publish")
    def test_reaction_added_ai(self, mock_publish):
        from voteit.reactions.messages import ReactionCount

        self.assertFalse(mock_publish.called)
        self._mk_reaction()
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ReactionCount)
        self.assertEqual(1, msg.data.count)
        self.assertEqual(self.button.pk, msg.data.button)
        self.assertEqual(self.prop.pk, msg.data.object_id)
        self.assertEqual("proposal", msg.data.content_type)

    @patch.object(AgendaItemChannel, "sync_publish")
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
        self.assertEqual("proposal", msg.data.content_type)

    @patch.object(UserChannel, "sync_publish")
    def test_reaction_added_user(self, mock_publish):
        from voteit.reactions.messages import UserReactionChanged

        self.assertFalse(mock_publish.called)
        reaction = self._mk_reaction()
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, UserReactionChanged)
        self.assertEqual(reaction.pk, msg.data.pk)
        self.assertEqual(self.button.pk, msg.data.button)
        self.assertEqual(self.prop.pk, msg.data.object_id)
        self.assertEqual("proposal", msg.data.content_type)

    @patch.object(UserChannel, "sync_publish")
    def test_reaction_deleted_user(self, mock_publish):
        from voteit.reactions.messages import UserReactionDeleted

        self.assertFalse(mock_publish.called)
        reaction = self._mk_reaction()
        reaction_pk = reaction.pk
        reaction.delete()
        msg = mock_publish.mock_calls[-1].args[0]
        self.assertIsInstance(msg, UserReactionDeleted)
        self.assertEqual(reaction_pk, msg.data.pk)

    def test_deleting_context_kills_reaction(self):
        # Due to historic reasons, reactions are linked to base object

        prop_ct = ContentType.objects.get_for_model(Proposal)
        disc_ct = ContentType.objects.get_for_model(DiscussionPost)
        diff_prop = DiffProposal.objects.create(
            agenda_item=self.ai, paragraph=self.para
        )
        diff_react = self.button.reactions.create(
            content_type=prop_ct,
            object_id=diff_prop.pk,
            agenda_item=self.ai,
            user=self.user,
        )
        prop_react = self.button.reactions.create(
            content_type=prop_ct,
            object_id=self.prop.pk,
            agenda_item=self.ai,
            user=self.user,
        )
        disc_react = self.button.reactions.create(
            content_type=disc_ct,
            object_id=self.disc.pk,
            agenda_item=self.ai,
            user=self.user,
        )
        for target, reaction in (
            (self.prop, prop_react),
            (self.disc, disc_react),
            (diff_prop, diff_react),
        ):
            with self.subTest(f"Reaction should disappear when {target} is deleted"):
                target.delete()
                self.assertRaises(
                    ObjectDoesNotExist,
                    reaction.refresh_from_db,
                )
