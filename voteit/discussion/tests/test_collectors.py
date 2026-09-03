from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from voteit.discussion.collectors import discussion_post_payloads
from voteit.discussion.messages import DiscussionPostChanged
from voteit.discussion.rest_api.serializers import DiscussionPostDetailSerializer
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.messaging.testing import assert_frames_equal
from voteit.messaging.testing import payloads_of
from voteit.messaging.testing import run_collector
from voteit.messaging.testing import testing_channel_layers_setting
from voteit.messaging.values import wire_field_names

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class DiscussionPostWireShapeTests(TestCase):
    """`discussion.posts` builds payloads with .values(), not the serializer.

    Safe only while DiscussionPostDetailSerializer stays free of method fields
    and nested serializers, so the equivalence is asserted rather than assumed.
    """

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create(title="M")
        cls.user = User.objects.create(username="u")
        cls.meeting.add_roles(cls.user, ROLE_PARTICIPANT)
        cls.group = cls.meeting.groups.create(title="G", groupid="g")
        cls.ai = cls.meeting.agenda_items.create(state="upcoming")
        # created is a datetime, the field most likely to serialise differently
        # between the two routes; tags exercises the ArrayField.
        cls.ai.discussions.create(body="First", author=cls.user, tags=["a", "b"])
        cls.ai.discussions.create(
            body="Second", author=cls.user, meeting_group=cls.group, as_group=True
        )

    @property
    def posts(self):
        return self.ai.discussions.order_by("pk")

    def test_values_matches_the_serializer(self):
        """Byte-for-byte identical frames, whichever route built them."""
        assert_frames_equal(
            self,
            DiscussionPostChanged,
            discussion_post_payloads(self.posts),
            DiscussionPostDetailSerializer(self.posts, many=True).data,
        )

    def test_wire_fields_are_pinned(self):
        """Changing what goes on the wire must fail loudly, not silently.

        Two halves. ``.values()`` raises FieldError for anything that is not a
        column or an alias, so evaluating the queryset is the assertion for a
        method field. The field list is spelled out on purpose: renaming or
        dropping one is a wire-format change, and breaking here is how the
        person making it finds out.
        """
        list(discussion_post_payloads(self.posts))
        self.assertSetEqual(
            {
                "agenda_item",
                "as_group",
                "author",
                "body",
                "created",
                "meeting_group",
                "pk",
                "tags",
            },
            set(wire_field_names(DiscussionPostDetailSerializer)),
        )

    def test_collector_sends_every_post(self):
        state = run_collector("discussion.posts", self.ai, self.user)
        payloads = payloads_of(state, DiscussionPostChanged)
        self.assertEqual({p.pk for p in self.posts}, {p.pk for p in payloads})

    def test_collector_is_one_query(self):
        for i in range(5):
            self.ai.discussions.create(body=f"extra {i}", author=self.user)
        with self.assertNumQueries(1):
            run_collector("discussion.posts", self.ai, self.user)
