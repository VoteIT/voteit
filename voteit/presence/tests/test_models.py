from django.db import IntegrityError
from django.test import TestCase


class PresenceCheckTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create()

    def test_save_duplicate(self):
        first = self.meeting.presence_checks.create()
        # Updating should of course not complain
        first.close()
        first.save()
        # This is open
        self.meeting.presence_checks.create()
        # Another open not ok
        self.assertRaises(IntegrityError, self.meeting.presence_checks.create)
