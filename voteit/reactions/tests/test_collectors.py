from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.messaging.testing import assert_frames_equal
from voteit.messaging.testing import payloads_of
from voteit.messaging.testing import run_collector
from voteit.messaging.testing import testing_channel_layers_setting
from voteit.messaging.values import wire_field_names
from voteit.reactions.collectors import button_payloads
from voteit.reactions.collectors import reaction_payloads
from voteit.reactions.messages import ButtonChanged
from voteit.reactions.messages import UserReactionChanged
from voteit.reactions.rest_api.serializers import ButtonDetailSerializer
from voteit.reactions.rest_api.serializers import ReactionSerializer

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class ReactionWireShapeTests(TestCase):
    """`reactions.buttons` and `reactions.own` build payloads with .values().

    `reactions.own` is the one case where this is a bug fix rather than a
    tuning choice: ReactionSerializer renders content_type with a CharField
    subclass, which gets none of DRF's pk-only optimisation and loaded a
    ContentType per row.
    """

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create(title="M")
        cls.user = User.objects.create(username="u")
        cls.meeting.add_roles(cls.user, ROLE_PARTICIPANT)
        cls.ai = cls.meeting.agenda_items.create(state="upcoming")
        cls.button = cls.meeting.reaction_buttons.create(
            title="Like",
            change_roles=[ROLE_PARTICIPANT.name],
            list_roles=[ROLE_PARTICIPANT.name],
        )
        cls.other_button = cls.meeting.reaction_buttons.create(title="Dislike")
        cls.proposals = [cls.ai.proposals.create() for _ in range(3)]
        for prop in cls.proposals:
            # agenda_item is a nullable FK the generic relation does not fill in
            prop.reaction_set.create(
                button=cls.button, user=cls.user, agenda_item=cls.ai
            )

    @property
    def buttons(self):
        return self.meeting.reaction_buttons.order_by("pk")

    @property
    def own_reactions(self):
        return self.ai.reactions.filter(user=self.user).order_by("pk")

    def test_button_values_matches_the_serializer(self):
        """Byte-for-byte identical frames, whichever route built them."""
        assert_frames_equal(
            self,
            ButtonChanged,
            button_payloads(self.buttons),
            ButtonDetailSerializer(self.buttons, many=True).data,
        )

    def test_reaction_values_matches_the_serializer(self):
        assert_frames_equal(
            self,
            UserReactionChanged,
            reaction_payloads(self.own_reactions),
            ReactionSerializer(self.own_reactions, many=True).data,
        )

    def test_wire_fields_are_pinned(self):
        """Changing what goes on the wire must fail loudly, not silently.

        Two halves. ``.values()`` raises FieldError for anything that is not a
        column or an alias, so evaluating the queryset is the assertion for a
        method field. The field list is spelled out on purpose: renaming or
        dropping one is a wire-format change, and breaking here is how the
        person making it finds out.
        """
        list(button_payloads(self.buttons))
        list(reaction_payloads(self.own_reactions))
        self.assertSetEqual(
            {
                "active",
                "allowed_models",
                "change_roles",
                "color",
                "description",
                "flag_mode",
                "icon",
                "list_roles",
                "meeting",
                "on_presentation",
                "on_vote",
                "order",
                "pk",
                "target",
                "title",
                "vote_template",
            },
            set(wire_field_names(ButtonDetailSerializer)),
        )
        self.assertSetEqual(
            {"agenda_item", "button", "content_type", "object_id", "pk", "user"},
            set(wire_field_names(ReactionSerializer)),
        )

    def test_content_type_is_a_shortname_not_a_pk(self):
        """UserReactionResponseSchema validates it, so a raw pk would be rejected."""
        payloads = list(reaction_payloads(self.own_reactions))
        self.assertEqual({"proposal"}, {p["content_type"] for p in payloads})

    def test_own_reactions_is_one_query(self):
        """It was one query per reaction: the ContentType FK per row."""
        for prop in self.ai.proposals.create(), self.ai.proposals.create():
            prop.reaction_set.create(
                button=self.other_button, user=self.user, agenda_item=self.ai
            )
        with self.assertNumQueries(1):
            list(reaction_payloads(self.own_reactions))

    def test_own_collector_sends_every_reaction(self):
        state = run_collector("reactions.own", self.ai, self.user)
        payloads = payloads_of(state, UserReactionChanged)
        self.assertEqual({r.pk for r in self.own_reactions}, {p.pk for p in payloads})

    def test_buttons_collector_sends_every_button(self):
        state = run_collector(
            "reactions.buttons",
            self.meeting,
            self.user,
            channel_cls=ParticipantsChannel,
        )
        payloads = payloads_of(state, ButtonChanged)
        self.assertEqual({b.pk for b in self.buttons}, {p.pk for p in payloads})
