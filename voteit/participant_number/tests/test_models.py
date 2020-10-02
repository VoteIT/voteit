from django.db import IntegrityError
from django.test import TestCase


class ParticipantNumberTests(TestCase):

    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.participant_number.models import PNSystem
        self.meeting = Meeting.objects.create()
        self.user_pn = self.meeting.participants.create(username="pn")
        self.user_no_pn = self.meeting.participants.create(username="404")
        self.system = PNSystem.objects.create(meeting=self.meeting)
        self.pn = self.system.numbers.create(user=self.user_pn, number=1)

    def test_get_user(self):
        self.assertEqual(self.user_pn, self.system.get_user(1))
        self.assertIsNone(self.system.get_user(2))

    def test_duplicate_pn(self):
        self.assertRaises(IntegrityError, self.system.numbers.create, user=self.user_no_pn, number=1)
