from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from voteit.messaging.testing import action_of
from voteit.messaging.testing import build_app_state
from voteit.messaging.testing import ChannelMessageCatcher
from voteit.messaging.testing import testing_channel_layers_setting

from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.organisation.models import Organisation
from voteit.participant_tags.components import GenderTags
from voteit.participant_tags.components import NamespacedTags
from voteit.participant_tags.components import PronounTags
from voteit.participant_tags.messages import AllParticipantTags
from voteit.participant_tags.messages import ParticipantTagsChanged

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
            enabled=True,
        )
        cls.gender_component: NamespacedTags = cls.meeting.components.create(
            component_name=GenderTags.name,
            settings={"tags": ["f", "m", "nb"]},
            enabled=True,
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
        command = build_app_state(
            MeetingChannel.name, self.meeting.pk, self.participant.pk
        )
        app_state = command
        tags_payload = [
            x.payload for x in app_state if x.action == action_of(AllParticipantTags)
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
        self.assertEqual(
            {
                "meeting": self.meeting.pk,
                "tags": {},
                "user": self.moderator.pk,
            },
            messages[0].data.dict(),
        )
