from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.collectors import group_membership_payloads
from voteit.meeting.collectors import group_role_payloads
from voteit.meeting.collectors import meeting_group_payloads
from voteit.meeting.messages import GroupMembershipChanged
from voteit.meeting.messages import GroupRoleChanged
from voteit.meeting.messages import MeetingGroupChanged
from voteit.meeting.models import GroupMembership
from voteit.meeting.models import Meeting
from voteit.meeting.rest_api.serializers import GroupMembershipSerializer
from voteit.meeting.rest_api.serializers import GroupRoleSerializer
from voteit.meeting.rest_api.serializers import MeetingGroupSerializer
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.messaging.testing import assert_frames_equal
from voteit.messaging.testing import payloads_of
from voteit.messaging.testing import run_collector
from voteit.messaging.testing import testing_channel_layers_setting
from voteit.messaging.values import wire_field_names

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class MeetingGroupWireShapeTests(TestCase):
    """`meeting.groups` and `meeting.group_roles` build payloads with .values().

    Safe only while these serializers stay free of method fields and nested
    serializers, so the equivalence is asserted rather than assumed.
    """

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create(title="M", group_roles_active=True)
        cls.user = User.objects.create(username="u")
        cls.other = User.objects.create(username="o")
        for u in (cls.user, cls.other):
            cls.meeting.add_roles(u, ROLE_PARTICIPANT)
        cls.delegate = cls.meeting.groups.create(title="Delegate", groupid="delegate")
        cls.group = cls.meeting.groups.create(
            title="G",
            groupid="g",
            body="Body",
            tags=["x"],
            votes=3,
            delegate_to=cls.delegate,
        )
        cls.role = cls.meeting.group_roles.create(
            title="R", roles=[ROLE_PARTICIPANT.name]
        )
        GroupMembership.objects.create(meeting_group=cls.group, user=cls.user)
        GroupMembership.objects.create(meeting_group=cls.delegate, user=cls.other)

    @property
    def groups(self):
        return self.meeting.groups.order_by("pk")

    @property
    def memberships(self):
        return GroupMembership.objects.filter(
            meeting_group__meeting=self.meeting
        ).order_by("pk")

    @property
    def roles(self):
        return self.meeting.group_roles.order_by("pk")

    def test_group_values_matches_the_serializer(self):
        assert_frames_equal(
            self,
            MeetingGroupChanged,
            meeting_group_payloads(self.groups),
            MeetingGroupSerializer(self.groups, many=True).data,
        )

    def test_membership_values_matches_the_serializer(self):
        assert_frames_equal(
            self,
            GroupMembershipChanged,
            group_membership_payloads(self.memberships),
            GroupMembershipSerializer(self.memberships, many=True).data,
        )

    def test_role_values_matches_the_serializer(self):
        """`roles` is a RolesField over an ArrayField -- same list either way."""
        assert_frames_equal(
            self,
            GroupRoleChanged,
            group_role_payloads(self.roles),
            GroupRoleSerializer(self.roles, many=True).data,
        )

    def test_wire_fields_are_pinned(self):
        """Changing what goes on the wire must fail loudly, not silently.

        Two halves. ``.values()`` raises FieldError for anything that is not a
        column or an alias, so evaluating the queryset is the assertion for a
        method field. The field list is spelled out on purpose: renaming or
        dropping one is a wire-format change, and breaking here is how the
        person making it finds out.
        """
        list(meeting_group_payloads(self.groups))
        list(group_membership_payloads(self.memberships))
        list(group_role_payloads(self.roles))
        self.assertSetEqual(
            {
                "body",
                "delegate_to",
                "groupid",
                "meeting",
                "pk",
                "post_as",
                "show_on_speaker",
                "tags",
                "title",
                "votes",
            },
            set(wire_field_names(MeetingGroupSerializer)),
        )
        self.assertSetEqual(
            {"meeting_group", "pk", "role", "user", "votes"},
            set(wire_field_names(GroupMembershipSerializer)),
        )
        self.assertSetEqual(
            {"meeting", "pk", "role_id", "roles", "title"},
            set(wire_field_names(GroupRoleSerializer)),
        )

    def test_collector_still_injects_the_meeting_pk(self):
        state = run_collector(
            "meeting.groups", self.meeting, self.user, channel_cls=ParticipantsChannel
        )
        payloads = payloads_of(state, GroupMembershipChanged)
        self.assertEqual(2, len(payloads))
        self.assertEqual({self.meeting.pk}, {p.m for p in payloads})

    def test_groups_collector_does_not_query_per_group(self):
        """delegate_to is a FK read as a pk -- no prefetch, no per-row query."""

        def queries(n_extra):
            for i in range(n_extra):
                self.meeting.groups.create(title=f"x{i}", groupid=f"x{i}")
            with self.assertNumQueries(2) as ctx:
                run_collector(
                    "meeting.groups",
                    self.meeting,
                    self.user,
                    channel_cls=ParticipantsChannel,
                )
            return ctx

        # Two queries: the groups and the memberships. Constant in group count.
        queries(0)
        queries(5)
