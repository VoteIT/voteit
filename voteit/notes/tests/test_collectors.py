from django.test import TestCase
from django.test import override_settings

from voteit.meeting.models import Meeting
from voteit.messaging.channels import UserChannel
from voteit.messaging.testing import ChannelMessageCatcher
from voteit.messaging.testing import assert_frames_equal
from voteit.messaging.testing import payloads_of
from voteit.messaging.testing import run_collector
from voteit.messaging.testing import testing_channel_layers_setting
from voteit.notes import NoteIntent
from voteit.messaging.values import wire_field_names
from voteit.notes.collectors import note_payloads
from voteit.notes.components import NotesComponent
from voteit.notes.messages import NoteChanged
from voteit.notes.rest_api.serializers import NoteSerializer


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class NoteWireShapeTests(TestCase):
    """`note.changed` payloads are built with .values(), not NoteSerializer.

    That is only safe while the serializer stays free of method fields and
    nested serializers, so the equivalence is asserted rather than assumed --
    the same guard `agenda.items` has. The collector and the post_save signal
    now share one builder; before this they spelled the eight fields out
    independently, and NoteSerializer spelled them a third time.
    """

    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.participant = cls.meeting.participants.get(username="participant")
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop = cls.ai.proposals.create()
        cls.note = cls.participant.notes.create(
            proposal=cls.prop,
            intent=NoteIntent.APPROVE,
            body="Not sure about this one",
        )
        # A second note, so an ordering difference between the two routes
        # would show up rather than being invisible at n=1.
        cls.other = cls.participant.notes.create(
            proposal=cls.ai.proposals.create(), intent=NoteIntent.DENY
        )
        cls.meeting.components.create(component_name=NotesComponent.name, enabled=True)

    @property
    def notes(self):
        return self.participant.notes.filter(proposal__agenda_item=self.ai)

    def test_values_matches_the_serializer(self):
        """Byte-for-byte identical frames, whichever route built them."""
        assert_frames_equal(
            self,
            NoteChanged,
            note_payloads(self.notes),
            NoteSerializer(self.notes.select_related("proposal"), many=True).data,
        )

    def test_wire_fields_are_pinned(self):
        """Changing what goes on the wire must fail loudly, not silently.

        Two halves. ``.values()`` raises FieldError for anything that is not a
        column or an alias, so evaluating the queryset is the assertion for a
        method field. The field list is spelled out on purpose: renaming or
        dropping one is a wire-format change, and breaking here is how the
        person making it finds out.
        """
        list(note_payloads(self.notes))
        self.assertSetEqual(
            {
                "agenda_item",
                "body",
                "created",
                "intent",
                "meeting",
                "pk",
                "proposal",
                "user",
            },
            set(wire_field_names(NoteSerializer)),
        )

    def test_collector_matches_the_signal(self):
        """The initial state and the push describe a note the same way."""
        with ChannelMessageCatcher(UserChannel, NoteChanged) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                self.note.save()
        self.assertEqual(1, len(messages))
        from_signal = messages[0].payload.model_dump(mode="json")

        state = run_collector("notes.notes", self.ai, self.participant)
        from_collector = [
            p.model_dump(mode="json") for p in payloads_of(state, NoteChanged)
        ]
        self.assertIn(from_signal, from_collector)

    def test_collector_stays_at_two_queries(self):
        """One for the component gate, one for the notes -- never per note."""
        for _ in range(5):
            self.participant.notes.create(proposal=self.ai.proposals.create())
        with self.assertNumQueries(2):
            run_collector("notes.notes", self.ai, self.participant)
