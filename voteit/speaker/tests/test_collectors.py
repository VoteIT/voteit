from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.statemachines import MeetingStateMachine
from voteit.messaging.registry import batch_for
from voteit.messaging.testing import ChannelMessageCatcher
from voteit.messaging.testing import action_of
from voteit.messaging.testing import payloads_of
from voteit.messaging.testing import run_collector
from voteit.messaging.testing import testing_channel_layers_setting
from voteit.room.channels import RoomChannel
from voteit.speaker.collectors import SPEAKER_ANNOTATIONS
from voteit.speaker.collectors import SPEAKER_FIELDS
from voteit.speaker.collectors import speaker_payloads
from voteit.speaker.messages import SpeakerChanged
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.rest_api.serializers import SpeakerSerializer
from voteit.speaker.roles import ROLE_SPEAKER

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class SpeakerWireShapeTests(TestCase):
    """`speaker.changed` payloads are built with .values(), not SpeakerSerializer.

    That is only safe while the serializer stays free of method fields and
    nested serializers, so the equivalence is asserted rather than assumed --
    the same guard `agenda.items` has. `notify_active_list_changed` used to
    rebuild the serializer's six keys by hand, so a field added to
    SpeakerSerializer reached the collector and the single-speaker push but
    silently skipped the active-list batch; both now share one builder.
    """

    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.meeting.state = MeetingStateMachine.ongoing.value
        cls.meeting.save()
        cls.participant = cls.meeting.participants.get(username="participant")
        cls.room = cls.meeting.rooms.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.system: SpeakerListSystem = SpeakerListSystem.objects.create(
            method_name="simple", room=cls.room
        )
        cls.system.add_roles(cls.participant, ROLE_SPEAKER)
        cls.speaker_list: SpeakerList = SpeakerList.objects.create(
            speaker_system=cls.system, agenda_item=cls.ai, title="Hello"
        )
        cls.speaker = cls.speaker_list.speaker_items.create(user=cls.participant)

    def test_values_matches_the_serializer(self):
        """Byte-for-byte identical frames, whichever route built them."""
        # Speaker has no Meta.ordering, so pin one -- otherwise the two
        # executions are free to disagree about row order.
        qs = Speaker.objects.filter(speaker_list=self.speaker_list).order_by("pk")
        batch_cls = batch_for(SpeakerChanged)
        from_values = batch_cls(payload={"items": list(speaker_payloads(qs))})
        from_serializer = batch_cls(
            payload={
                "items": SpeakerSerializer(
                    qs.select_related("speaker_list"), many=True
                ).data
            }
        )
        self.assertEqual(
            from_serializer.model_dump(mode="json"),
            from_values.model_dump(mode="json"),
        )

    def test_field_list_tracks_the_serializer(self):
        self.assertEqual(
            set(SpeakerSerializer.Meta.fields),
            set(SPEAKER_FIELDS) | set(SPEAKER_ANNOTATIONS),
        )

    def test_every_field_is_a_concrete_column(self):
        """A method field added to the serializer must fail loudly, not silently."""
        # .values() raises FieldError for anything that is not a column or an
        # alias, so simply evaluating the queryset is the assertion.
        list(speaker_payloads(Speaker.objects.filter(speaker_list=self.speaker_list)))

    def test_signal_matches_the_collector(self):
        """The active-list batch and the initial state agree, field for field."""
        self.system.active_list = None
        self.system.save()
        batch_action = f"{action_of(SpeakerChanged)}.batch"
        with ChannelMessageCatcher(RoomChannel, batch_action) as messages:
            self.system.active_list = self.speaker_list
            self.system.save()
        from_signal = [
            p.model_dump(mode="json") for p in payloads_of(messages, SpeakerChanged)
        ]

        room = self.meeting.rooms.get(pk=self.room.pk)
        state = run_collector("speaker.active_list", room, self.participant)
        from_collector = [
            p.model_dump(mode="json") for p in payloads_of(state, SpeakerChanged)
        ]
        self.assertEqual(1, len(from_signal))
        self.assertEqual(from_signal, from_collector)

    def test_batch_does_not_query_per_speaker(self):
        """`room` comes from a join, not a query per row."""

        def queries_to_activate() -> int:
            # Fresh instances each round: SpeakerListSerializer caches the
            # list's speakers on the SpeakerList it is handed, which would
            # otherwise make the second round cheaper for the wrong reason.
            system = SpeakerListSystem.objects.get(pk=self.system.pk)
            system.active_list = None
            system.save()
            system = SpeakerListSystem.objects.get(pk=self.system.pk)
            with CaptureQueriesContext(connection) as ctx:
                system.active_list = SpeakerList.objects.get(pk=self.speaker_list.pk)
                system.save()
            return len(ctx)

        with_one = queries_to_activate()
        for i in range(3):
            user = User.objects.create(username=f"speaker-{i}")
            self.meeting.add_roles(user, ROLE_PARTICIPANT)
            self.speaker_list.speaker_items.create(user=user)
        self.assertEqual(with_one, queries_to_activate())
