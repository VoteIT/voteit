from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.agenda.channels import AgendaItemChannel
from voteit.meeting.channels import MeetingChannel

User = get_user_model()


class SignalListOrderChangeTests(TestCase):
    def setUp(self):

        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.system = SpeakerListSystem.objects.create(
            method_name="simple", meeting=self.meeting
        )
        self.speaker_list = SpeakerList.objects.create(
            list_system=self.system, agenda_item=self.ai
        )
        self.user_one = User.objects.create(username="one")
        self.user_two = User.objects.create(username="two")
        self.user_three = User.objects.create(username="three")
        self.speaker_one = self.speaker_list.speaker_items.create(user=self.user_one)
        self.speaker_two = self.speaker_list.speaker_items.create(user=self.user_two)
        self.speaker_three = self.speaker_list.speaker_items.create(
            user=self.user_three
        )

    @patch.object(AgendaItemChannel, "publish")
    def test_agenda_gets_list_change(self, mock_publish):
        self.speaker_list.signal_list_updated()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        data = msg.data
        self.assertEqual(
            [self.user_one.pk, self.user_two.pk, self.user_three.pk], data.queue
        )
        self.assertEqual(self.speaker_list.pk, data.pk)
        self.assertIsNone(data.current)

    @patch.object(MeetingChannel, "publish")
    def test_meeting_gets_active_list(self, mock_publish):
        self.system.active_list = self.speaker_list
        self.system.save()
        self.speaker_list.signal_list_updated()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        data = msg.data
        self.assertEqual(
            [self.user_one.pk, self.user_two.pk, self.user_three.pk], data.queue
        )
        self.assertEqual(self.speaker_list.pk, data.pk)
        self.assertIsNone(data.current)

    @patch.object(AgendaItemChannel, "publish")
    def test_agenda_with_active_speaker(self, mock_publish):
        self.speaker_three.start()
        # self.speaker_list.current = self.speaker_three
        self.speaker_list.save()
        self.speaker_list.signal_list_updated()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[-1].args[0]
        data = msg.data
        self.assertEqual([self.user_one.pk, self.user_two.pk], data.queue)
        self.assertEqual(self.speaker_list.pk, data.pk)
        self.assertEqual(self.user_three.pk, data.current)


class SignalAddedOrChangedTests(TestCase):
    def setUp(self):

        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.system = SpeakerListSystem.objects.create(
            method_name="simple", meeting=self.meeting
        )
        self.speaker_list = SpeakerList.objects.create(
            list_system=self.system, agenda_item=self.ai, title="Hello"
        )

    @patch.object(AgendaItemChannel, "publish")
    def test_agenda_gets_list_changed(self, mock_publish):
        from voteit.speaker.messages import SpeakerListAdded

        speaker_list = self.system.speaker_lists.create(agenda_item=self.ai)
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, SpeakerListAdded)
        data = msg.data
        self.assertEqual("open", data.state)
        self.assertEqual(self.system.pk, data.list_system)
        self.assertEqual(speaker_list.pk, data.pk)
        self.assertEqual(self.ai.pk, data.agenda_item)

    @patch.object(MeetingChannel, "publish")
    def test_meeting_gets_active_list_changed(self, mock_publish):
        from voteit.speaker.messages import SpeakerListChanged

        self.system.active_list = self.speaker_list
        self.system.save()
        self.speaker_list.title = "world"
        self.speaker_list.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        data = msg.data
        self.assertIsInstance(msg, SpeakerListChanged)
        self.assertEqual(self.system.pk, data.list_system)
        self.assertEqual(self.ai.pk, data.agenda_item)
        self.assertEqual(self.speaker_list.title, data.title)
