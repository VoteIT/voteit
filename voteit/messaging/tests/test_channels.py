"""Who may subscribe to what.

allow_subscribe is the whole access check for a channel: the subscribe job
calls it once and then joins the group. These paths are otherwise only
reached through a live socket and an RQ worker, so they are covered here
directly.
"""

from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from voteit.meeting.channels import MeetingChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.messaging.channels import ONLINE_GROUP
from voteit.messaging.channels import OnlineChannel
from voteit.messaging.channels import UserChannel
from voteit.messaging.channels import user_group
from voteit.messaging.testing import testing_channel_layers_setting
from voteit.organisation.models import Organisation

from .test_jobs import receive_or_none

User = get_user_model()


class UserChannelTests(TestCase):
    """A user's own channel: the one place a pk *is* the permission."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="owner")
        cls.other = User.objects.create(username="other")

    def test_owner_may_subscribe(self):
        self.assertTrue(UserChannel(self.user.pk).allow_subscribe(self.user))

    def test_another_user_may_not(self):
        self.assertFalse(UserChannel(self.user.pk).allow_subscribe(self.other))

    def test_anonymous_may_not(self):
        self.assertFalse(UserChannel(self.user.pk).allow_subscribe(None))

    def test_an_unsaved_user_may_not(self):
        """Guards pk None == pk None, which would otherwise match."""
        self.assertFalse(UserChannel(None).allow_subscribe(User()))

    def test_group_name_matches_what_the_consumer_joins(self):
        self.assertEqual(
            user_group(self.user.pk), UserChannel(self.user.pk).channel_name
        )

    def test_model_is_bound_at_app_ready(self):
        """It cannot be set at class-creation time -- see the app config."""
        self.assertIs(User, UserChannel.model)


class ContextChannelPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create(title="Org", host="testserver")
        cls.meeting = Meeting.objects.create(
            title="Meeting", organisation=cls.organisation
        )
        cls.moderator = User.objects.create(username="moderator")
        cls.participant = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)

    def test_permission_is_checked_against_the_context(self):
        channel = ModeratorsChannel(self.meeting.pk)
        self.assertTrue(channel.allow_subscribe(self.moderator))
        self.assertFalse(channel.allow_subscribe(self.participant))

    def test_anonymous_is_refused_before_the_permission_lookup(self):
        self.assertFalse(ModeratorsChannel(self.meeting.pk).allow_subscribe(None))

    def test_a_channel_without_a_permission_lets_anyone_in(self):
        class OpenChannel(MeetingChannel):
            name = "open-for-testing"
            permission = None

        self.assertTrue(OpenChannel(self.meeting.pk).allow_subscribe(None))

    def test_missing_context_raises_does_not_exist(self):
        """The subscribe and recheck jobs both rely on catching this."""
        channel = MeetingChannel(self.meeting.pk + 1000)
        with self.assertRaises(Meeting.DoesNotExist):
            channel.allow_subscribe(self.moderator)

    def test_from_instance_skips_the_lookup(self):
        channel = MeetingChannel.from_instance(self.meeting)
        with self.assertNumQueries(0):
            self.assertEqual(self.meeting, channel.context)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class SubscribeLeaveTests(TestCase):
    consumer_channel = "specific.abcdef!ghijkl"

    def test_subscribe_then_leave(self):
        layer = get_channel_layer()
        channel = MeetingChannel(1, consumer_channel=self.consumer_channel)

        async_to_sync(channel.subscribe)()
        async_to_sync(layer.group_send)("meeting_1", {"type": "x"})
        self.assertIsNotNone(receive_or_none(layer, self.consumer_channel))

        async_to_sync(channel.leave)()
        async_to_sync(layer.group_send)("meeting_1", {"type": "x"})
        self.assertIsNone(receive_or_none(layer, self.consumer_channel))


class OnlineChannelTests(TestCase):
    def test_group_name_is_shared_by_every_socket(self):
        self.assertEqual(ONLINE_GROUP, OnlineChannel().channel_name)
