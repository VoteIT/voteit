from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.dispatch import receiver
from django.test import TestCase
from django.test import override_settings

from envelope.messages.channels import Subscribe
from envelope.messages.channels import Subscribed
from voteit.core.testing import FakeCommit
from voteit.meeting.models import GroupRole
from voteit.meeting.models import Meeting
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import MeetingGroup
from voteit.organisation.models import Organisation
from voteit.poll.app.er_policies.auto_before_poll import AutoBeforePoll

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


class MeetingJoinedSignalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.user = User.objects.create(username="user")

    @property
    def _fut(self):
        from voteit.meeting.signals import meeting_joined

        return meeting_joined

    def test_signal_sent(self):
        L = []

        @receiver(self._fut)
        def my_listener(**kw):
            L.append(kw)

        with FakeCommit():
            self.meeting.add_roles(self.user, "participant")
            self.assertFalse(L)
        self.assertTrue(L)
        kwargs = L[0]
        self.assertEqual(self.meeting, kwargs.pop("meeting"))
        self.assertEqual(self.user, kwargs.pop("user"))
        self.assertEqual({"participant"}, set(kwargs.pop("meeting_roles").assigned))

    def test_signal_send_after_invite_used(self):
        @receiver(self._fut)
        def my_listener(user, **kw):
            one = self.meeting.invites.filter(user_data={"boo": "Hoo"}).first()
            self.assertEqual(one.state, "accepted")

        invite = self.meeting.invites.create(user_data={"boo": "Hoo"})
        with FakeCommit():
            invite.accept(self.user)
            invite.save()


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class MeetingChangedTests(TestCase):
    def setUp(self):
        self.meeting = Meeting.objects.create()

    # We don't handle added right now
    @patch.object(MeetingChannel, "sync_publish")
    def test_changed(self, mock_publish):
        from voteit.meeting.messages import MeetingChanged

        self.assertFalse(mock_publish.called)
        self.meeting.title = "Hello"
        self.meeting.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        msg.validate()
        self.assertIsInstance(msg, MeetingChanged)
        self.assertEqual(self.meeting.pk, msg.data.pk)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class MeetingChannelSubscribedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.user: User = cls.meeting.participants.create(username="user")
        cls.meeting.add_roles(cls.user, "moderator")
        cls.group: MeetingGroup = cls.meeting.groups.create(title="Gang")
        cls.group_role: GroupRole = cls.meeting.group_roles.create(
            title="President", role_id="president"
        )
        cls.group_membership = cls.group.memberships.create(
            role=cls.group_role, user=cls.user
        )

    def _mk_subscribe(self):
        return Subscribe(
            mm={"user_pk": self.user.pk, "consumer_name": "abc"},
            channel_type="meeting",
            pk=self.meeting.pk,
        )

    def test_roles_in_app_state(self):
        msg = self._mk_subscribe()
        msg.validate()
        response = msg.run_job()
        self.assertIsInstance(response, Subscribed)
        added_meeting_roles = [
            x
            for x in response.data.app_state
            if x.t == "roles.added" and x.p["pk"] == self.meeting.pk
        ]
        self.assertEqual(1, len(added_meeting_roles))
        payload = added_meeting_roles[0].p
        self.assertEqual(set(payload["roles"]), {"participant", "moderator"})
        self.assertEqual(payload["user_pk"], self.user.pk)
        self.assertEqual(payload["model"], "meeting")

    def test_meeting_groups_and_related_in_app_state(self):
        self.meeting.group_roles_active = True
        self.meeting.save()
        msg = self._mk_subscribe()
        msg.validate()
        response = msg.run_job()
        self.assertIsInstance(response, Subscribed)
        # MeetingGroup
        added = [x for x in response.data.app_state if x.t == "meeting_group.added"]
        self.assertEqual(1, len(added))
        payload = added[0].p
        self.assertEqual(self.group.pk, payload["pk"])
        # GroupRole
        added = [x for x in response.data.app_state if x.t == "group_role.added"]
        self.assertEqual(1, len(added))
        payload = added[0].p
        self.assertEqual(self.group_role.pk, payload["pk"])
        # GroupMembership
        added = [x for x in response.data.app_state if x.t == "group_membership.added"]
        self.assertEqual(1, len(added))
        payload = added[0].p
        self.assertEqual(self.group_membership.pk, payload["pk"])


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class MeetingGroupChangedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.group = cls.meeting.groups.create()
        cls.user = User.objects.create(username="maybe_member")

    @patch.object(MeetingChannel, "sync_publish")
    def test_added(self, mock_publish):
        from voteit.meeting.messages import MeetingGroupAdded

        with FakeCommit():
            group = self.meeting.groups.create()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        msg.validate()
        self.assertIsInstance(msg, MeetingGroupAdded)
        self.assertEqual(group.pk, msg.data.pk)

    @patch.object(MeetingChannel, "sync_publish")
    def test_changed(self, mock_publish):
        from voteit.meeting.messages import MeetingGroupChanged

        with FakeCommit():
            self.group.title = "Hello"
            self.group.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        msg.validate()
        self.assertIsInstance(msg, MeetingGroupChanged)
        self.assertEqual(self.group.pk, msg.data.pk)

    @patch.object(MeetingChannel, "sync_publish")
    def test_deleted(self, mock_publish):
        from voteit.meeting.messages import MeetingGroupDeleted

        group_pk = self.group.pk
        self.group.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        msg.validate()
        self.assertIsInstance(msg, MeetingGroupDeleted)
        self.assertEqual(group_pk, msg.data.pk)

    @patch.object(MeetingChannel, "sync_publish")
    def test_member_added_compat(self, mock_publish):
        from voteit.meeting.messages import GroupMembershipAdded

        self.group.members.add(self.user)
        self.assertTrue(mock_publish.called)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertIsInstance(msg, GroupMembershipAdded)
        self.assertEqual(self.group.pk, msg.data.meeting_group)

    @patch.object(MeetingChannel, "sync_publish")
    def test_member_added_compat_reverse(self, mock_publish):
        from voteit.meeting.messages import GroupMembershipAdded

        self.user.meeting_groups.add(self.group)
        self.assertTrue(mock_publish.called)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertIsInstance(msg, GroupMembershipAdded)
        self.assertEqual(self.group.pk, msg.data.meeting_group)

    @patch.object(MeetingChannel, "sync_publish")
    def test_member_removed_compat(self, mock_publish):
        from voteit.meeting.messages import GroupMembershipDeleted

        self.group.members.add(self.user)
        mock_publish.reset_mock()
        self.group.members.remove(self.user)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertIsInstance(msg, GroupMembershipDeleted)

    @patch.object(MeetingChannel, "sync_publish")
    def test_member_removed_compat_reverse(self, mock_publish):
        from voteit.meeting.messages import GroupMembershipDeleted

        self.user.meeting_groups.add(self.group)
        mock_publish.reset_mock()
        self.user.meeting_groups.remove(self.group)
        self.assertTrue(mock_publish.called)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertIsInstance(msg, GroupMembershipDeleted)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class RoleChangesPublishedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        org: Organisation = Organisation.objects.create()
        cls.meeting: Meeting = org.meetings.create()
        cls.user = cls.meeting.participants.create(username="user", organisation=org)
        cls.meeting.add_roles(cls.user, "participant")

    @patch.object(MeetingChannel, "sync_publish")
    def test_added(self, mock_publish):
        from voteit.core.messages.role_updates import RolesAdded

        self.assertFalse(mock_publish.called)
        self.meeting.add_roles(self.user, "moderator")
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, RolesAdded)
        self.assertEqual(self.meeting.pk, msg.data.pk)
        self.assertEqual({"moderator"}, set(msg.data.roles))

    @patch.object(MeetingChannel, "sync_publish")
    def test_removed(self, mock_publish):
        from voteit.core.messages.role_updates import RolesRemoved

        self.assertFalse(mock_publish.called)
        self.meeting.remove_roles(self.user, "participant")
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, RolesRemoved)
        self.assertEqual(self.meeting.pk, msg.data.pk)
        self.assertEqual({"participant"}, set(msg.data.roles))


class MeetingERChangedTests(TestCase):
    @property
    def _fut(self):
        from voteit.meeting.signals import er_policy_changed

        return er_policy_changed

    def test_er_changed_not_sent_when_added(self):
        L = []

        @receiver(self._fut)
        def my_listener(**kw):
            L.append(kw)

        Meeting.objects.create(er_policy_name=AutoBeforePoll.name)
        self.assertEqual([], L)

    def test_er_changed_to_none(self):
        L = []

        @receiver(self._fut)
        def my_listener(**kw):
            L.append(kw)

        m = Meeting.objects.create(er_policy_name=AutoBeforePoll.name)
        m.er_policy_name = None
        m.save()
        self.assertEqual([], L)

    def test_er_changed(self):
        L = []

        @receiver(self._fut)
        def my_listener(**kw):
            L.append(kw)

        m = Meeting.objects.create()
        m.er_policy_name = AutoBeforePoll.name
        m.save()
        self.assertEqual(1, len(L))
        kwargs = L[0]
        self.assertEqual(AutoBeforePoll, kwargs["sender"])
