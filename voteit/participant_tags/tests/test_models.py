from django.db import IntegrityError
from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.participant_tags.components import GenderTags


class ParticipantTagTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.participant = cls.meeting.participants.get(username="participant")
        cls.moderator = cls.meeting.participants.get(username="moderator")
        cls.component = cls.meeting.components.create(
            component_name=GenderTags.name,
            enabled=True,
            settings_data={"tags": ["f", "m", "nb"]},
        )

    def test_valid(self):
        self.assertTrue(self.component.is_valid)
        self.component.settings_data["tags"] = []
        self.assertFalse(self.component.is_valid)

    def test_duplicate_constraint(self):
        self.meeting.participant_tags.create(user=self.participant)
        self.meeting.participant_tags.create(user=self.moderator)
        with self.assertRaises(IntegrityError):
            self.meeting.participant_tags.create(user=self.participant)
