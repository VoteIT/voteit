from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.messaging.testing import assert_frames_equal
from voteit.messaging.testing import testing_channel_layers_setting
from voteit.messaging.values import wire_field_names
from voteit.poll.collectors import vote_transfer_payloads
from voteit.poll.messages import VoteTransferChanged
from voteit.poll.models import VoteTransfer
from voteit.poll.rest_api.serializers import VoteTransferSerializer

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class VoteTransferWireShapeTests(TestCase):
    """`poll.vote_transfers` builds payloads with .values(), not the serializer.

    `meeting`, `source` and `target` are declared fields rather than generated
    ones, so the equivalence is worth asserting: they happen to be RelatedFields
    over concrete FK columns, which is what makes .values() a substitute.
    """

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create(title="M")
        cls.users = []
        for name in ("a", "b", "c", "d"):
            user = User.objects.create(username=name)
            cls.meeting.add_roles(user, ROLE_PARTICIPANT)
            cls.users.append(user)
        VoteTransfer.objects.create(
            meeting=cls.meeting, source=cls.users[0], target=cls.users[1]
        )
        VoteTransfer.objects.create(
            meeting=cls.meeting, source=cls.users[2], target=cls.users[3]
        )

    @property
    def transfers(self):
        return self.meeting.vote_transfers.order_by("pk")

    def test_values_matches_the_serializer(self):
        """Byte-for-byte identical frames, whichever route built them."""
        assert_frames_equal(
            self,
            VoteTransferChanged,
            vote_transfer_payloads(self.transfers),
            VoteTransferSerializer(self.transfers, many=True).data,
        )

    def test_wire_fields_are_pinned(self):
        """Changing what goes on the wire must fail loudly, not silently.

        Two halves. ``.values()`` raises FieldError for anything that is not a
        column or an alias, so evaluating the queryset is the assertion for a
        method field. The field list is spelled out on purpose: renaming or
        dropping one is a wire-format change, and breaking here is how the
        person making it finds out.
        """
        list(vote_transfer_payloads(self.transfers))
        self.assertSetEqual(
            {"meeting", "pk", "source", "target"},
            set(wire_field_names(VoteTransferSerializer)),
        )

    def test_is_one_query(self):
        with self.assertNumQueries(1):
            list(vote_transfer_payloads(self.transfers))
