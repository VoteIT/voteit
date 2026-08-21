from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from voteit.agenda.collectors import AGENDA_ITEM_FIELDS
from voteit.agenda.collectors import AgendaItems
from voteit.agenda.messages import AgendaChanged
from voteit.agenda.rest_api.serializers import AgendaItemListSerializer
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.messaging.registry import batch_for
from voteit.messaging.state import AppState
from voteit.messaging.testing import payloads_of
from voteit.messaging.testing import run_collector
from voteit.messaging.testing import testing_channel_layers_setting

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class AgendaItemsCollectorTests(TestCase):
    """`agenda.items` builds payloads with .values() instead of the serializer.

    That is only safe while the serializer stays free of method fields and
    nested serializers, so the equivalence is asserted rather than assumed.
    """

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create(title="M")
        cls.moderator = User.objects.create(username="mod")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR, ROLE_PARTICIPANT)
        cls.public = cls.meeting.agenda_items.create(
            title="Public", state="upcoming", tags=["a", "b"]
        )
        cls.private = cls.meeting.agenda_items.create(title="Private")
        cls.blocked = cls.meeting.agenda_items.create(
            title="Blocked",
            state="ongoing",
            block_discussion=True,
            block_proposals=True,
        )
        # related_modified is a datetime, the field most likely to serialise
        # differently between the two routes.
        cls.public.maybe_mark_related_modified()
        cls.public.refresh_from_db()

    def test_values_matches_the_serializer(self):
        """Byte-for-byte identical frames, whichever route built them."""
        qs = self.meeting.agenda_items.all()
        batch_cls = batch_for(AgendaChanged)
        from_values = batch_cls(payload={"items": list(qs.values(*AGENDA_ITEM_FIELDS))})
        from_serializer = batch_cls(
            payload={"items": AgendaItemListSerializer(qs, many=True).data}
        )
        self.assertEqual(
            from_serializer.model_dump(mode="json"),
            from_values.model_dump(mode="json"),
        )

    def test_field_list_tracks_the_serializer(self):
        self.assertEqual(
            tuple(AgendaItemListSerializer.Meta.fields), AGENDA_ITEM_FIELDS
        )

    def test_every_field_is_a_concrete_column(self):
        """A method field added to the serializer must fail loudly, not silently."""
        # .values() raises FieldError for anything that is not a column, so
        # simply evaluating the queryset is the assertion.
        list(self.meeting.agenda_items.values(*AGENDA_ITEM_FIELDS))

    def test_moderators_see_private_items(self):
        state = run_collector(
            "agenda.items", self.meeting, self.moderator, channel_cls=ModeratorsChannel
        )
        titles = {p.title for p in payloads_of(state, AgendaChanged)}
        self.assertEqual({"Public", "Private", "Blocked"}, titles)

    def test_participants_do_not(self):
        state = run_collector(
            "agenda.items",
            self.meeting,
            self.moderator,
            channel_cls=ParticipantsChannel,
        )
        titles = {p.title for p in payloads_of(state, AgendaChanged)}
        self.assertEqual({"Public", "Blocked"}, titles)

    def test_no_model_instances_are_built(self):
        """The point of .values(): no AgendaItem, so no state machine per row."""
        created = []
        original = AgendaItems.collect

        from voteit.agenda.models import AgendaItem

        real_init = AgendaItem.__init__

        def counting_init(self, *args, **kwargs):
            created.append(1)
            return real_init(self, *args, **kwargs)

        AgendaItem.__init__ = counting_init
        try:
            state = AppState()
            collector = AgendaItems(
                ModeratorsChannel.from_instance(self.meeting), self.moderator
            )
            original(collector, state)
        finally:
            AgendaItem.__init__ = real_init
        self.assertEqual(3, len(payloads_of(state, AgendaChanged)))
        self.assertEqual([], created)
