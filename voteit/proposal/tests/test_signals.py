from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from voteit.agenda.channels import AgendaItemChannel
from voteit.messaging.messages.channels import Subscribe

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AgendaSubscribedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.ai.upcoming()
        self.ai.save()
        self.prop1 = self.ai.proposals.create()
        self.prop2 = self.ai.proposals.create()
        self.user = User.objects.create(username="user")
        self.meeting.add_roles(self.user, "participant")

    def test_app_state_sent(self):
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.ai.pk,
            channel_type="agenda_item",
        )
        msg = command.run_job()
        pks = set([x.p["pk"] for x in msg.data.app_state if x.t == "proposal.added"])
        self.assertEqual({self.prop1.pk, self.prop2.pk}, pks)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ProposalChangedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.prop = self.ai.proposals.create()

    @patch.object(AgendaItemChannel, "publish")
    def test_added(self, mock_publish):
        from voteit.proposal.messages import ProposalAdded

        self.assertFalse(mock_publish.called)
        prop = self.ai.proposals.create()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalAdded)
        self.assertEqual(prop.pk, msg.data.pk)

    @patch.object(AgendaItemChannel, "publish")
    def test_changed(self, mock_publish):
        from voteit.proposal.messages import ProposalChanged

        self.assertFalse(mock_publish.called)
        self.prop.body = "Hello"
        self.prop.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalChanged)
        self.assertEqual(self.prop.pk, msg.data.pk)

    @patch.object(AgendaItemChannel, "publish")
    def test_deleted(self, mock_publish):
        from voteit.proposal.messages import ProposalDeleted

        self.assertFalse(mock_publish.called)
        prop_pk = self.prop.pk
        self.prop.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalDeleted)
        self.assertEqual(prop_pk, msg.data.pk)
