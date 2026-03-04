from django.test import TestCase
from django.test import override_settings
from envelope.app.user_channel.channel import UserChannel
from envelope.channels.messages import Subscribe
from envelope.channels.models import AppState
from envelope.messages.common import Batch
from envelope.testing import ChannelMessageCatcher
from envelope.testing import testing_channel_layers_setting

from voteit.agenda.channels import AgendaItemChannel
from voteit.core.workflows import EnabledWf
from voteit.meeting.models import Meeting
from voteit.notes import NoteIntent
from voteit.notes.components import NotesComponent
from voteit.notes.messages import NoteAdded
from voteit.notes.messages import NoteChanged
from voteit.notes.messages import NoteDeleted


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class SignalTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.participant = cls.meeting.participants.get(username="participant")
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.prop3 = cls.ai.proposals.create()
        cls.note = cls.participant.notes.create(
            proposal=cls.prop,
            intent=NoteIntent.APPROVE,
        )
        cls.component = cls.meeting.components.create(
            component_name=NotesComponent.name, state=EnabledWf.ON
        )

    def _mk_subs(self):
        return Subscribe(
            mm={"user_pk": self.participant.pk, "consumer_name": "abc"},
            channel_type=AgendaItemChannel.name,
            pk=self.ai.pk,
        )

    def test_msg_on_add(self):
        with ChannelMessageCatcher(UserChannel, NoteAdded) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                self.participant.notes.create(
                    proposal=self.prop2,
                    intent=NoteIntent.APPROVE,
                )
        self.assertEqual(1, len(messages))
        data = messages[0].data.dict()
        self.assertIsInstance(data.pop("pk"), int)
        self.assertIsInstance(data.pop("created"), str)
        self.assertEqual(
            {
                "m": self.meeting.pk,
                "ai": self.ai.pk,
                "user": self.participant.pk,
                "p": self.prop2.pk,
                "intent": NoteIntent.APPROVE,
                "body": "",
            },
            data,
        )

    def test_msg_on_change(self):
        with ChannelMessageCatcher(UserChannel, NoteChanged) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                self.note.body = "I really don't know about this"
                self.note.save()
        self.assertEqual(1, len(messages))
        data = messages[0].data.dict()
        self.assertIsInstance(data.pop("created"), str)
        self.assertEqual(
            {
                "pk": self.note.pk,
                "m": self.meeting.pk,
                "ai": self.ai.pk,
                "user": self.participant.pk,
                "p": self.prop.pk,
                "intent": str(NoteIntent.APPROVE),
                "body": "I really don't know about this",
            },
            data,
        )

    def test_msg_on_delete(self):
        note_pk = self.note.pk
        with ChannelMessageCatcher(UserChannel, NoteDeleted) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                self.note.delete()
        self.assertEqual(1, len(messages))
        data = messages[0].data.dict()
        self.assertEqual(
            {"pk": note_pk},
            data,
        )

    def test_subscribe(self):
        msg = self._mk_subs()
        ch = AgendaItemChannel(self.ai.pk)
        app_state = msg.get_app_state(ch)
        batch_msg = [
            x for x in app_state if x["t"] == Batch.name and x["p"].t == NoteAdded.name
        ]
        self.assertEqual(1, len(batch_msg))
        batch_msg = batch_msg[0]
        data_one = batch_msg["p"].payloads[0].dict()
        self.assertIsInstance(data_one.pop("created"), str)
        self.assertEqual(
            {
                "p": self.prop.pk,
                "m": self.meeting.pk,
                "ai": self.ai.pk,
                "pk": self.note.pk,
                "body": "",
                "user": self.participant.pk,
                "intent": str(NoteIntent.APPROVE),
            },
            data_one,
        )

    def test_subscribe_no_component(self):
        self.component.delete()
        msg = self._mk_subs()
        ch = AgendaItemChannel(self.ai.pk)
        app_state = msg.get_app_state(ch)
        batch_msg = [
            x for x in app_state if x["t"] == Batch.name and x["p"].t == NoteAdded.name
        ]
        self.assertEqual(0, len(batch_msg))

    def test_subscribe_n1(self):
        from voteit.notes.signals import send_notes_appstruct

        self.participant.notes.create(
            proposal=self.prop2,
            intent=NoteIntent.APPROVE,
        )
        self.participant.notes.create(
            proposal=self.prop3,
            intent=NoteIntent.APPROVE,
        )
        app_state = AppState()
        with self.assertNumQueries(2):
            send_notes_appstruct(
                context=self.ai, user=self.participant, app_state=app_state
            )
