from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.dispatch import receiver
from django.test import TestCase
from django.test import override_settings
from voteit.messaging.testing import build_app_state
from voteit.messaging.testing import testing_channel_layers_setting

from voteit.meeting.models import GroupMembership
from voteit.meeting.models import GroupRole
from voteit.meeting.models import Meeting
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import MeetingGroup
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.organisation.models import Organisation
from voteit.poll.app.er_policies.auto_before_poll import AutoBeforePoll

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
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

        with self.captureOnCommitCallbacks(execute=True):
            self.meeting.add_roles(self.user, ROLE_PARTICIPANT)
            self.assertFalse(L)
        self.assertTrue(L)
        kwargs = L[0]
        self.assertEqual(self.meeting, kwargs.pop("meeting"))
        self.assertEqual(self.user, kwargs.pop("user"))
        self.assertEqual({ROLE_PARTICIPANT}, set(kwargs.pop("meeting_roles").assigned))

    def test_signal_send_after_invite_used(self):
        from voteit.invites.models import MeetingInvite

        @receiver(self._fut)
        def my_listener(user, **kw):
            one = self.meeting.invites.filter(user_data={"boo": "Hoo"}).first()
            self.assertIsInstance(one, MeetingInvite)
            self.assertEqual(one.state, "accepted")

        invite = self.meeting.invites.create(user_data={"boo": "Hoo"})
        with self.captureOnCommitCallbacks(execute=True):
            invite.accept(self.user)
            invite.save()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
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
        self.assertIsInstance(msg, MeetingChanged)
        self.assertEqual(self.meeting.pk, msg.payload.pk)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class MeetingChannelSubscribedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.user: User = cls.meeting.participants.create(username="user")
        cls.meeting.add_roles(cls.user, ROLE_MODERATOR)
        cls.group: MeetingGroup = cls.meeting.groups.create(title="Gang")
        cls.group_role: GroupRole = cls.meeting.group_roles.create(
            title="President", role_id="president"
        )
        cls.group_membership = cls.group.memberships.create(
            role=cls.group_role, user=cls.user
        )

    def _mk_subscribe(self):
        return build_app_state("meeting", self.meeting.pk, self.user.pk)

    def test_roles_in_app_state(self):
        app_state = self._mk_subscribe()
        added_meeting_roles = [
            x
            for x in app_state
            if x.action == "roles.changed" and x.payload.pk == self.meeting.pk
        ]
        self.assertEqual(1, len(added_meeting_roles))
        payload = added_meeting_roles[0].payload
        self.assertEqual(set(payload.roles), {ROLE_MODERATOR, ROLE_PARTICIPANT})
        self.assertEqual(payload.user_pk, self.user.pk)
        self.assertEqual(payload.model, "meeting")

    def test_meeting_groups_and_related_in_app_state(self):
        self.meeting.group_roles_active = True
        self.meeting.save()
        app_state = self._mk_subscribe()
        # MeetingGroup
        added = [x for x in app_state if x.action == "meeting_group.changed.batch"]
        self.assertEqual(1, len(added))
        payload = added[0].payload.items[0]
        self.assertEqual(self.group.pk, payload.pk)
        # GroupRole
        added = [x for x in app_state if x.action == "group_role.changed"]
        self.assertEqual(1, len(added))
        payload = added[0].payload
        self.assertEqual(self.group_role.pk, payload.pk)
        # GroupMembership
        added = [x for x in app_state if x.action == "group_membership.changed.batch"]
        self.assertEqual(1, len(added))
        payload = added[0].payload.items[0]
        self.assertEqual(self.group_membership.pk, payload.pk)
        self.assertEqual(self.meeting.pk, payload.m)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class MeetingGroupChangedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.group = cls.meeting.groups.create()
        cls.user = cls.meeting.participants.create(username="maybe_member")
        cls.meeting.add_roles(cls.user, ROLE_PARTICIPANT)

    @patch.object(MeetingChannel, "sync_publish")
    def test_added(self, mock_publish):
        from voteit.meeting.messages import MeetingGroupChanged

        with self.captureOnCommitCallbacks(execute=True):
            group = self.meeting.groups.create()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingGroupChanged)
        self.assertEqual(group.pk, msg.payload.pk)

    @patch.object(MeetingChannel, "sync_publish")
    def test_changed(self, mock_publish):
        from voteit.meeting.messages import MeetingGroupChanged

        with self.captureOnCommitCallbacks(execute=True):
            self.group.title = "Hello"
            self.group.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingGroupChanged)
        self.assertEqual(self.group.pk, msg.payload.pk)

    @patch.object(MeetingChannel, "sync_publish")
    def test_deleted(self, mock_publish):
        from voteit.meeting.messages import MeetingGroupDeleted

        group_pk = self.group.pk
        self.group.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingGroupDeleted)
        self.assertEqual(group_pk, msg.payload.pk)

    @patch.object(MeetingChannel, "sync_publish")
    def test_member_added_compat(self, mock_publish):
        from voteit.meeting.messages import GroupMembershipChanged

        self.group.members.add(self.user)
        self.assertTrue(mock_publish.called)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        msg = messages[0]
        self.assertIsInstance(msg, GroupMembershipChanged)
        self.assertEqual(self.group.pk, msg.payload.meeting_group)
        self.assertEqual(self.meeting.pk, msg.payload.m)

    @patch.object(MeetingChannel, "sync_publish")
    def test_member_added_compat_reverse(self, mock_publish):
        from voteit.meeting.messages import GroupMembershipChanged

        self.user.meeting_groups.add(self.group)
        self.assertTrue(mock_publish.called)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        msg = messages[0]
        self.assertIsInstance(msg, GroupMembershipChanged)
        self.assertEqual(self.group.pk, msg.payload.meeting_group)
        self.assertEqual(self.meeting.pk, msg.payload.m)

    @patch.object(MeetingChannel, "sync_publish")
    def test_member_removed_compat(self, mock_publish):
        from voteit.meeting.messages import GroupMembershipDeleted

        self.group.members.add(self.user)
        mock_publish.reset_mock()
        self.group.members.remove(self.user)
        messages = [x.args[0] for x in mock_publish.mock_calls]
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
        msg = messages[0]
        self.assertIsInstance(msg, GroupMembershipDeleted)

    def test_membership_removed_when_user_kicked_from_meeting(self):
        self.user.meeting_groups.add(self.group)
        self.assertTrue(
            GroupMembership.objects.filter(
                user=self.user, meeting_group=self.group
            ).exists()
        )
        self.meeting.remove_roles(self.user, ROLE_PARTICIPANT)
        self.assertFalse(
            GroupMembership.objects.filter(
                user=self.user, meeting_group=self.group
            ).exists()
        )


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class RoleChangesPublishedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        org: Organisation = Organisation.objects.create()
        cls.meeting: Meeting = org.meetings.create()
        cls.user = cls.meeting.participants.create(username="user", organisation=org)
        cls.meeting.add_roles(cls.user, ROLE_PARTICIPANT)

    @patch.object(MeetingChannel, "sync_publish")
    def test_added(self, mock_publish):
        from voteit.core.messages.role_updates import RolesChanged

        self.assertFalse(mock_publish.called)
        self.meeting.add_roles(self.user, ROLE_MODERATOR)
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, RolesChanged)
        self.assertEqual(self.meeting.pk, msg.payload.pk)
        self.assertEqual({ROLE_MODERATOR}, set(msg.payload.roles))

    @patch.object(MeetingChannel, "sync_publish")
    def test_removed(self, mock_publish):
        from voteit.core.messages.role_updates import RolesRemoved

        self.assertFalse(mock_publish.called)
        self.meeting.remove_roles(self.user, ROLE_PARTICIPANT)
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, RolesRemoved)
        self.assertEqual(self.meeting.pk, msg.payload.pk)
        self.assertEqual({ROLE_PARTICIPANT}, set(msg.payload.roles))


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
