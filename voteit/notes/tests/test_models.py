from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.test import override_settings

from voteit.messaging.testing import testing_channel_layers_setting

from voteit.meeting.models import Meeting

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class NotesTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.participant = cls.meeting.participants.get(username="participant")
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop = cls.ai.proposals.create()

    @property
    def _cut(self):
        from voteit.notes.models import Note

        return Note

    def _mk_one(self, **kwargs):
        kwargs.setdefault("proposal", self.prop)
        kwargs.setdefault("user", self.participant)
        return self._cut.objects.create(**kwargs)

    def test_note_adds_meeting(self):
        note = self._mk_one()
        self.assertEqual(note.meeting, self.meeting)

    def test_duplicate(self):
        self._mk_one()
        with self.assertRaises(IntegrityError):
            self._mk_one()
