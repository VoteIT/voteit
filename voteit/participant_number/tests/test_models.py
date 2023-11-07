from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.participant_number.models import PNSystem

User = get_user_model()


class ParticipantNumberTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.user_pn = User.objects.create(username="pn")
        cls.user_no_pn = User.objects.create(username="404")
        cls.meeting.add_roles(cls.user_pn, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.user_no_pn, ROLE_PARTICIPANT)
        cls.system = PNSystem.objects.create(meeting=cls.meeting)
        cls.pn = cls.system.numbers.create(user=cls.user_pn, number=1)

    def test_get_user(self):
        self.assertEqual(self.user_pn, self.system.get_user(1))
        self.assertIsNone(self.system.get_user(2))

    def test_duplicate_pn(self):
        self.assertRaises(
            IntegrityError, self.system.numbers.create, user=self.user_no_pn, number=1
        )

    def test_duplicate_user(self):
        self.assertRaises(
            IntegrityError, self.system.numbers.create, user=self.user_pn, number=2
        )
