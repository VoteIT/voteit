from collections import Counter
from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.test import override_settings
from voteit.agenda.messages import AgendaChanged

from voteit.messaging.testing import MessageCatcher
from voteit.messaging.testing import action_of
from voteit.messaging.testing import build_app_state
from voteit.messaging.testing import testing_channel_layers_setting

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.messages import AgendaBodyChanged
from voteit.agenda.messages import LastReadChanged
from voteit.agenda.models import AgendaItem
from voteit.core.testing import FakeCommit
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class SubscribedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(
            body="Hello world", state="upcoming"
        )
        cls.ai_private: AgendaItem = cls.meeting.agenda_items.create()
        cls.user = User.objects.create(username="user")
        cls.meeting.add_roles(cls.user, ROLE_MODERATOR)
        cls.ai_private.mark_read(cls.user)

    def test_app_state_sent_participants(self):
        app_state = build_app_state(
            ParticipantsChannel.name, self.meeting.pk, self.user.pk
        )
        pks = set()
        for msg in app_state:
            if msg.action == "agenda_item.changed.batch":
                pks = {x.pk for x in msg.payload.items}
        self.assertEqual({self.ai.pk}, pks)

    def test_app_state_sent_moderators(self):
        app_state = build_app_state(
            ModeratorsChannel.name, self.meeting.pk, self.user.pk
        )
        pks = set()
        for msg in app_state:
            if msg.action == "agenda_item.changed.batch":
                pks = {x.pk for x in msg.payload.items}
        self.assertEqual({self.ai.pk, self.ai_private.pk}, pks)

    def test_app_state_last_read_sent(self):
        command = build_app_state(
            ParticipantsChannel.name, self.meeting.pk, self.user.pk
        )
        ch = ParticipantsChannel(self.meeting.pk)
        self.assertTrue(ch.allow_subscribe(self.user))
        app_state = command
        batch_msgs = [
            x for x in app_state if x.action == f"{action_of(LastReadChanged)}.batch"
        ]
        self.assertEqual(1, len(batch_msgs))
        batch = batch_msgs[0]
        self.assertEqual(
            {self.ai_private.pk}, {x.agenda_item for x in batch.payload.items}
        )

    def test_app_state_sends_body(self):
        command = build_app_state(AgendaItemChannel.name, self.ai.pk, self.user.pk)
        ch = AgendaItemChannel(self.ai.pk)
        self.assertTrue(ch.allow_subscribe(self.user))
        app_state = command
        messages = [x for x in app_state if x.action == action_of(AgendaBodyChanged)]
        msg = messages[0]
        self.assertEqual(
            {"pk": self.ai.pk, "body": "Hello world"}, msg.payload.model_dump()
        )


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class AgendaChangedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.ai_pk = cls.ai.pk

    def setUp(self):
        self.ai = self.meeting.agenda_items.get(pk=self.ai_pk)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_added_participants(self, mock_publish):
        # This should have no effect at all
        self.assertFalse(mock_publish.called)
        self.meeting.agenda_items.create()
        self.assertFalse(mock_publish.called)

    @patch.object(ModeratorsChannel, "sync_publish")
    def test_added_moderators(self, mock_publish):
        from voteit.agenda.messages import AgendaChanged

        self.assertFalse(mock_publish.called)
        ai = self.meeting.agenda_items.create()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, AgendaChanged)
        self.assertEqual(ai.pk, msg.payload.pk)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_changed_participants(self, mock_publish):
        from voteit.agenda.messages import AgendaChanged

        self.assertFalse(mock_publish.called)
        self.ai.title = "Hello"
        self.ai.save()
        # Still private, so nothing sent
        self.assertFalse(mock_publish.called)
        self.ai.state = "upcoming"
        self.ai.save()
        # But now it's published
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, AgendaChanged)
        self.assertEqual(self.ai.pk, msg.payload.pk)

    def test_changed_causes_batch_messages(self):
        ais = []
        with FakeCommit():  # Also clears callbacks
            for i in range(5):
                ais.append(self.meeting.agenda_items.create(title=str(i)))

        # Five changes to the same channel in one transaction collapse into a
        # single agenda_item.changed.batch on commit.
        with MessageCatcher() as messages:
            with self.captureOnCommitCallbacks(execute=True):
                for ai in ais:
                    ai.title += " updated"
                    ai.save()
        counter = Counter(m.action for m in messages)
        self.assertEqual(1, counter[f"{action_of(AgendaChanged)}.batch"])
        self.assertEqual(0, counter[action_of(AgendaChanged)])
        batch = next(
            m for m in messages if m.action == f"{action_of(AgendaChanged)}.batch"
        )
        self.assertEqual(5, len(batch.payload.items))

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_deleted_moderators(self, mock_publish):
        from voteit.agenda.messages import AgendaDeleted

        self.assertFalse(mock_publish.called)
        ai_pk = self.ai.pk
        self.ai.delete()
        self.assertTrue(mock_publish.called)
        # Agenda
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, AgendaDeleted)
        self.assertEqual(ai_pk, msg.payload.pk)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class DeleteWithContentTests(TestCase):
    def test_no_changed_after_deleted(self):
        """Deleting children in the cascade must not resurrect the item client side."""
        with FakeCommit():
            meeting = Meeting.objects.create()
            ai = meeting.agenda_items.create(state="upcoming")
            ai.proposals.create()
            ai.discussions.create()
        with MessageCatcher() as messages:
            with FakeCommit():
                ai.delete()
        actions = [m.action for m in messages if m.action.startswith("agenda_item.")]
        self.assertIn("agenda_item.deleted", actions)
        self.assertNotIn("agenda_item.changed", actions)


class ArchiveAgendaTests(TestCase):
    def setUp(self):
        self.meeting = Meeting.objects.create()
        self.meeting.agenda_items.create()

    def test_archive(self):
        self.meeting.archive()
        ai = self.meeting.agenda_items.first()
        self.assertEqual("archived", ai.state)


def _dt(msg: AgendaChanged) -> datetime:
    return datetime.fromisoformat(msg.payload.related_modified)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class RelatedItemsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # FakeCommit, or the pending push lingers in the class transaction and
        # swallows the ones the tests schedule.
        with FakeCommit():
            cls.meeting: Meeting = Meeting.objects.create()
            cls.ai: AgendaItem = cls.meeting.agenda_items.create(state="upcoming")
            cls.ai_private: AgendaItem = cls.meeting.agenda_items.create()
            cls.prop = cls.ai.proposals.create()
            cls.disc = cls.ai.discussions.create()

    def setUp(self):
        self.prop = self.ai.proposals.get(pk=self.prop.pk)
        self.disc = self.ai.discussions.get(pk=self.disc.pk)

    def _pushed(self, func, channel_cls=ParticipantsChannel) -> list[AgendaChanged]:
        with patch.object(channel_cls, "sync_publish") as mock_publish:
            with self.captureOnCommitCallbacks(execute=True):
                func()
        return [
            x.args[0]
            for x in mock_publish.mock_calls
            if x.args[0].action == "agenda_item.changed"
        ]

    def test_proposal_deleted(self):
        msgs = self._pushed(self.prop.delete)
        self.assertEqual(1, len(msgs))
        self.assertEqual(self.disc.created, _dt(msgs[0]))

    def test_discussion_deleted(self):
        msgs = self._pushed(self.disc.delete)
        self.assertEqual(1, len(msgs))
        self.assertEqual(self.prop.created, _dt(msgs[0]))

    def test_proposal_created(self):
        msgs = self._pushed(lambda: self.ai.proposals.create(body="Hello"))
        self.assertEqual(1, len(msgs))
        self.assertEqual(self.ai.proposals.latest("created").created, _dt(msgs[0]))

    def test_proposal_changed(self):
        self.prop.body = "Hello"
        self.assertFalse(self._pushed(self.prop.save))

    def test_discussion_created(self):
        msgs = self._pushed(lambda: self.ai.discussions.create(body="Hello"))
        self.assertEqual(1, len(msgs))

    def test_discussion_changed(self):
        self.disc.body = "Hello"
        self.assertFalse(self._pushed(self.disc.save))

    def test_private_only_to_moderators(self):
        # One capture only: executed callbacks stay in run_on_commit within a test
        with patch.object(ModeratorsChannel, "sync_publish") as mod_publish:
            msgs = self._pushed(
                lambda: self.ai_private.discussions.create(body="Hello")
            )
        self.assertFalse(msgs)
        self.assertEqual(1, len(mod_publish.mock_calls))

    def test_rollback_drops_push(self):
        def create_and_rollback():
            try:
                with transaction.atomic():
                    self.ai.proposals.create(body="Hello")
                    raise ValueError
            except ValueError:
                pass

        self.assertFalse(self._pushed(create_and_rollback))
