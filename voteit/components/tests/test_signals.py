from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from envelope.channels.messages import Subscribe
from envelope.channels.messages import Subscribed
from voteit.active.components import ActiveUsersComponent
from voteit.core.testing import FakeCommit
from voteit.core.workflows import EnabledWf
from voteit.components.app.components.message import FlashMessage
from voteit.components.app.components.proposal_print import ProposalPrint
from voteit.meeting.models import Meeting
from voteit.meeting.channels import MeetingChannel
from voteit.components.models import MeetingComponent

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class MeetingChannelSubscribedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.user: User = cls.meeting.participants.create(username="user")
        cls.meeting.add_roles(cls.user, "moderator")
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

    def test_meeting_components_in_app_state(self):
        msg = self._mk_subscribe()
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
                "is_valid": True,
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
                "is_valid": True,
            },
            payloads[1],
        )

    def test_meeting_components_bad_data(self):
        self.prop_print.disable()
        self.prop_print.save()
        self.flash.settings_data = {}
        self.flash.save()
        msg = self._mk_subscribe()
        response = msg.run_job()
        self.assertIsInstance(response, Subscribed)
        payloads = [
            x.p for x in response.data.app_state if x.t == "meeting_component.added"
        ]
        self.assertEqual(0, len(payloads))

    def test_meeting_components_disabled(self):
        self.flash.disable()
        self.flash.save()
        msg = self._mk_subscribe()
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
                "is_valid": True,
            },
            payloads[0],
        )


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
        from voteit.components.messages import MeetingComponentAdded

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
        from voteit.components.messages import MeetingComponentChanged

        with FakeCommit():
            self.component.enable()
            self.component.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingComponentChanged)
        self.assertEqual(self.component.pk, msg.data.pk)

    @patch.object(MeetingChannel, "sync_publish")
    def test_changed_disabled(self, mock_publish):
        from voteit.components.messages import MeetingComponentDeleted

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
        from voteit.components.messages import MeetingComponentDeleted

        component_pk = self.component.pk
        self.component.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingComponentDeleted)
        self.assertEqual(component_pk, msg.data.pk)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class MeetingComponentsDisabledWhenMeetingClosesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create(state="ongoing")
        cls.msg: MeetingComponent = cls.meeting.components.create(
            component_name=FlashMessage.name,
            settings={"msg": "Hello"},
            state=EnabledWf.ON,
        )
        cls.active: MeetingComponent = cls.meeting.components.create(
            component_name=ActiveUsersComponent.name,
            state=EnabledWf.ON,
        )

    def test_close_meeting(self):
        self.meeting.close()
        self.meeting.save()
        self.msg.refresh_from_db()
        self.active.refresh_from_db()
        self.assertEqual(EnabledWf.ON, self.msg.state)
        self.assertEqual(EnabledWf.OFF, self.active.state)
