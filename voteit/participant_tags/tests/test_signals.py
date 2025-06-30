from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from django.utils.timezone import now
from django_fsm import TransitionNotAllowed
from envelope.channels.messages import Subscribe
from envelope.channels.messages import Subscribed
from envelope.channels.models import ContextChannel
from envelope.testing import ChannelMessageCatcher
from envelope.testing import MessageCatcher
from envelope.testing import testing_channel_layers_setting

from voteit.agenda.channels import AgendaItemChannel
from voteit.core.messages.role_updates import RolesAdded
from voteit.core.testing import FakeCommit
from voteit.core.workflows import EnabledWf
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.workflows import MeetingWf
from voteit.organisation.models import Organisation
from voteit.participant_tags.components import GenderTags
from voteit.participant_tags.components import NamespacedTags
from voteit.participant_tags.components import PronounTags
from voteit.participant_tags.messages import AllParticipantTags
from voteit.participant_tags.messages import ParticipantTagsChanged
from voteit.room.channels import RoomChannel
from voteit.speaker.messages import SpeakerAdded
from voteit.speaker.messages import SpeakerChanged
from voteit.speaker.messages import SpeakerDeleted

from voteit.speaker.messages import SpeakerListAdded
from voteit.speaker.messages import SpeakerListChanged
from voteit.speaker.messages import SpeakerListDeleted
from voteit.speaker.messages import SpeakerSystemAdded
from voteit.speaker.messages import SpeakerSystemChanged
from voteit.speaker.messages import SpeakerSystemDeleted
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.roles import ROLE_LIST_MODERATOR
from voteit.speaker.roles import ROLE_SPEAKER
from voteit.speaker.workflows import SpeakerListWf
from voteit.speaker.workflows import SpeakerSystemWf

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class SignalAndSubscribeTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org: Organisation = Organisation.objects.get(pk=1)
        cls.meeting = Meeting.objects.get(pk=1)
        cls.pronoun_component: NamespacedTags = cls.meeting.components.create(
            component_name=PronounTags.name,
            settings={"tags": ["han", "hon", "hen"], "many": True},
            state=EnabledWf.ON,
        )
        cls.gender_component: NamespacedTags = cls.meeting.components.create(
            component_name=GenderTags.name,
            settings={"tags": ["f", "m", "nb"]},
            state=EnabledWf.ON,
        )
        cls.participant = cls.org.users.get(username="participant")
        cls.moderator = cls.org.users.get(username="moderator")
        cls.participant_tags = cls.participant.meeting_tags.create(
            meeting=cls.meeting,
            tags={PronounTags.namespace: ["hon"], GenderTags.namespace: "f"},
        )
        cls.moderator_tags = cls.moderator.meeting_tags.create(
            meeting=cls.meeting,
            tags={PronounTags.namespace: ["hon", "hen"], GenderTags.namespace: "nb"},
        )

    def test_ptags_to_meeting_ch(self):
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.participant.pk},
            pk=self.meeting.pk,
            channel_type=MeetingChannel.name,
        )
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertIsInstance(msg, Subscribed)
        tags_payload = [
            x.p for x in msg.data.app_state if x.t == AllParticipantTags.name
        ][0]
        self.assertEqual(
            {
                "tags": {
                    "gen:f": [self.participant.pk],
                    "pron:hon": [self.moderator.pk, self.participant.pk],
                    "gen:nb": [self.moderator.pk],
                    "pron:hen": [self.moderator.pk],
                },
                "meeting": self.meeting.pk,
            },
            tags_payload,
        )

    def test_changed(self):
        with ChannelMessageCatcher(MeetingChannel, ParticipantTagsChanged) as messages:
            self.moderator_tags.save()
        self.assertEqual(1, len(messages))
        self.assertEqual(
            {
                "meeting": self.meeting.pk,
                "tags": {"pron": ["hon", "hen"], "gen": "nb"},
                "user": self.moderator.pk,
            },
            messages[0].data.dict(),
        )

    def test_deleted_sent_as_changed(self):
        with ChannelMessageCatcher(MeetingChannel, ParticipantTagsChanged) as messages:
            self.moderator_tags.delete()
        self.assertEqual(1, len(messages))
        self.assertEqual(
            {
                "meeting": self.meeting.pk,
                "tags": {},
                "user": self.moderator.pk,
            },
            messages[0].data.dict(),
        )
