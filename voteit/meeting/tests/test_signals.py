from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.dispatch import receiver
from django.test import TestCase
from django.test import override_settings

from envelope.messages.channels import Subscribe
from envelope.messages.channels import Subscribed
from voteit.core.testing import FakeCommit
from voteit.core.workflows import EnabledWf
from voteit.meeting.app.components.message import FlashMessage
from voteit.meeting.app.components.proposal_print import ProposalPrint
from voteit.meeting.models import Meeting
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import MeetingComponent

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
            one = self.meeting.invites.filter(invite_data="blaha").first()
            self.assertEqual(one.state, "accepted")

        invite = self.meeting.invites.create(invite_data="blaha", created_by=self.user)
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
        cls.group = cls.meeting.groups.create(title="Gang")
        cls.group.members.add(cls.user)
        cls.flash = cls.meeting.components.create(
            component_name=FlashMessage.name,
            settings={"msg": "Hello!"},
            state=EnabledWf.ON,
        )
        cls.prop_print = cls.meeting.components.create(
            component_name=ProposalPrint.name, state=EnabledWf.ON
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

    def test_meeting_groups_in_app_state(self):
        msg = self._mk_subscribe()
        msg.validate()
        response = msg.run_job()
        self.assertIsInstance(response, Subscribed)
        added = [x for x in response.data.app_state if x.t == "meeting_group.added"]
        self.assertEqual(1, len(added))
        payload = added[0].p
        self.assertEqual(
            set(payload["members"]),
            {self.user.pk},
        )

    def test_meeting_components_in_app_state(self):
        msg = self._mk_subscribe()
        msg.validate()
        response = msg.run_job()
        self.assertIsInstance(response, Subscribed)
        payloads = [
            x.p for x in response.data.app_state if x.t == "meeting_component.added"
        ]
        self.assertEqual(2, len(payloads))
        self.assertEqual(
            {
                "pk": self.flash.pk,
                "settings": {"msg": "Hello!", "type": "info"},
                "meeting": self.meeting.pk,
                "component_name": FlashMessage.name,
                "state": EnabledWf.ON,
            },
            payloads[0],
        )
        self.assertEqual(
            {
                "pk": self.prop_print.pk,
                "settings": None,
                "meeting": self.meeting.pk,
                "component_name": ProposalPrint.name,
                "state": EnabledWf.ON,
            },
            payloads[1],
        )

    def test_meeting_components_bad_data(self):
        self.prop_print.disable()
        self.prop_print.save()
        self.flash.settings_data = {}
        self.flash.save()
        msg = self._mk_subscribe()
        msg.validate()
        response = msg.run_job()
        self.assertIsInstance(response, Subscribed)
        payloads = [
            x.p for x in response.data.app_state if x.t == "meeting_component.added"
        ]
        self.assertEqual(1, len(payloads))
        self.assertEqual(
            {
                "pk": self.flash.pk,
                "settings": None,
                "meeting": self.meeting.pk,
                "component_name": FlashMessage.name,
                "state": EnabledWf.ON,
            },
            payloads[0],
        )

    def test_meeting_components_disabled(self):
        self.flash.disable()
        self.flash.save()
        msg = self._mk_subscribe()
        msg.validate()
        response = msg.run_job()
        self.assertIsInstance(response, Subscribed)
        payloads = [
            x.p for x in response.data.app_state if x.t == "meeting_component.added"
        ]
        self.assertEqual(1, len(payloads))
        self.assertEqual(
            {
                "pk": self.prop_print.pk,
                "settings": None,
                "meeting": self.meeting.pk,
                "component_name": ProposalPrint.name,
                "state": EnabledWf.ON,
            },
            payloads[0],
        )


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class MeetingGroupChangedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.group = cls.meeting.groups.create()

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


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class MeetingComponentChangedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.component: MeetingComponent = cls.meeting.components.create(
            component_name=FlashMessage.name, settings={"msg": "Hello"}
        )

    @patch.object(MeetingChannel, "sync_publish")
    def test_added_disabled(self, mock_publish):
        with FakeCommit():
            component = self.meeting.components.create(
                component_name=ProposalPrint.name
            )
        self.assertFalse(mock_publish.called)

    @patch.object(MeetingChannel, "sync_publish")
    def test_added_enabled(self, mock_publish):
        from voteit.meeting.messages import MeetingComponentAdded

        with FakeCommit():
            component = self.meeting.components.create(
                component_name=ProposalPrint.name, state=EnabledWf.ON
            )
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingComponentAdded)
        self.assertEqual(component.pk, msg.data.pk)

    @patch.object(MeetingChannel, "sync_publish")
    def test_changed_enabled(self, mock_publish):
        from voteit.meeting.messages import MeetingComponentChanged

        with FakeCommit():
            self.component.enable()
            self.component.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingComponentChanged)
        self.assertEqual(self.component.pk, msg.data.pk)

    @patch.object(MeetingChannel, "sync_publish")
    def test_changed_disabled(self, mock_publish):
        from voteit.meeting.messages import MeetingComponentDeleted

        # For any disabled component, delete is always sent since frontend can't distinguish between
        # actual deleted or just disabled.
        # Unless we're editing the component itself, that distinction isn't relevant.
        with FakeCommit():
            self.component.settings = {"msg": "Bye"}
            self.component.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingComponentDeleted)
        self.assertEqual(self.component.pk, msg.data.pk)

    @patch.object(MeetingChannel, "sync_publish")
    def test_deleted(self, mock_publish):
        from voteit.meeting.messages import MeetingComponentDeleted

        component_pk = self.component.pk
        self.component.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingComponentDeleted)
        self.assertEqual(component_pk, msg.data.pk)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class RoleChangesPublishedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.organisation.models import Organisation

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
