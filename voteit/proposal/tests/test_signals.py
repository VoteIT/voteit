from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.messaging.messages.channels import Subscribe

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SubscribedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.ai.upcoming()
        self.ai.save()
        self.prop1 = self.ai.proposals.create()
        self.prop2 = self.ai.proposals.create()
        self.user = User.objects.create(username="user")
        self.meeting.add_roles(self.user, "moderator")

    def test_app_state_sent_moderators(self):
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type="moderators",
        )
        msg = command.run_job()
        pks = set([x.p["pk"] for x in msg.data.app_state if x.t == "proposal.added"])
        self.assertEqual({self.prop1.pk, self.prop2.pk}, pks)

    def test_app_state_sent_private_moderators(self):
        self.ai.unpublish()
        self.ai.save()
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type="moderators",
        )
        msg = command.run_job()
        pks = set([x.p["pk"] for x in msg.data.app_state if x.t == "proposal.added"])
        self.assertEqual({self.prop1.pk, self.prop2.pk}, pks)

    def test_app_state_sent_participants(self):
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type="participants",
        )
        msg = command.run_job()
        pks = set([x.p["pk"] for x in msg.data.app_state if x.t == "proposal.added"])
        self.assertEqual({self.prop1.pk, self.prop2.pk}, pks)

    def test_app_state_sent_private_participants(self):
        self.ai.unpublish()
        self.ai.save()
        command = Subscribe(
            {"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type="participants",
        )
        msg = command.run_job()
        app_state = msg.data.app_state
        if app_state is None:
            app_state = ()
        pks = set([x.p["pk"] for x in app_state if x.t == "proposal.added"])
        self.assertEqual(set(), pks)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ProposalChangedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.ai.upcoming()
        self.ai.save()
        self.prop = self.ai.proposals.create()

    @patch.object(ParticipantsChannel, "publish")
    def test_added_participant(self, mock_publish):
        from voteit.proposal.messages import ProposalAdded

        self.assertFalse(mock_publish.called)
        prop = self.ai.proposals.create()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalAdded)
        self.assertEqual(prop.pk, msg.data.pk)
        self.ai.unpublish()
        self.ai.save()
        mock_publish.reset_mock()
        self.ai.proposals.create()
        self.assertFalse(mock_publish.called)

    @patch.object(ModeratorsChannel, "publish")
    def test_added_moderator(self, mock_publish):
        from voteit.proposal.messages import ProposalAdded

        self.assertFalse(mock_publish.called)
        prop = self.ai.proposals.create()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalAdded)
        self.assertEqual(prop.pk, msg.data.pk)
        self.ai.unpublish()
        self.ai.save()
        mock_publish.reset_mock()
        self.ai.proposals.create()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalAdded)

    @patch.object(ParticipantsChannel, "publish")
    def test_changed_participant(self, mock_publish):
        from voteit.proposal.messages import ProposalChanged

        self.assertFalse(mock_publish.called)
        self.prop.body = "Hello"
        self.prop.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalChanged)
        self.assertEqual(self.prop.pk, msg.data.pk)
        self.ai.unpublish()
        self.ai.save()
        mock_publish.reset_mock()
        self.prop.body = "World"
        self.prop.save()
        self.assertFalse(mock_publish.called)

    @patch.object(ModeratorsChannel, "publish")
    def test_changed_moderator(self, mock_publish):
        from voteit.proposal.messages import ProposalChanged

        self.assertFalse(mock_publish.called)
        self.prop.body = "Hello"
        self.prop.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalChanged)
        self.assertEqual(self.prop.pk, msg.data.pk)
        self.ai.unpublish()
        self.ai.save()
        mock_publish.reset_mock()
        self.prop.body = "World"
        self.prop.save()
        self.assertTrue(mock_publish.called)

    @patch.object(ParticipantsChannel, "publish")
    def test_deleted_participants(self, mock_publish):
        from voteit.proposal.messages import ProposalDeleted

        self.assertFalse(mock_publish.called)
        prop_pk = self.prop.pk
        self.prop.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalDeleted)
        self.assertEqual(prop_pk, msg.data.pk)
        self.ai.unpublish()
        self.ai.save()
        prop = self.ai.proposals.create()
        mock_publish.reset_mock()
        prop.delete()
        self.assertFalse(mock_publish.called)

    @patch.object(ModeratorsChannel, "publish")
    def test_deleted_moderators(self, mock_publish):
        from voteit.proposal.messages import ProposalDeleted

        self.assertFalse(mock_publish.called)
        prop_pk = self.prop.pk
        self.prop.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalDeleted)
        self.assertEqual(prop_pk, msg.data.pk)
        self.ai.unpublish()
        self.ai.save()
        prop = self.ai.proposals.create()
        prop_pk = prop.pk
        mock_publish.reset_mock()
        prop.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, ProposalDeleted)
        self.assertEqual(prop_pk, msg.data.pk)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class PrivateAIPublishedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.ai.proposals.create(body="Hello")
        self.user = User.objects.create(username="user")
        self.meeting.add_roles(self.user, "participant")

    @patch.object(ParticipantsChannel, "publish")
    def test_ai_made_public(self, mock_publish):
        from voteit.agenda.messages import AgendaChanged
        from voteit.proposal.messages import ProposalAdded

        self.ai.upcoming()
        self.ai.save()

        self.assertTrue(mock_publish.called)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        self.assertEqual(1, len([x for x in messages if isinstance(x, AgendaChanged)]))
        self.assertEqual(1, len([x for x in messages if isinstance(x, ProposalAdded)]))
