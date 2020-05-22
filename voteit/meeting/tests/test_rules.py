from django.contrib.auth.models import User
from django.test import TestCase


class RulesTests(TestCase):

    def setUp(self):
        from voteit.meeting.models import Meeting
        self.meeting = Meeting.objects.create()
        self.user = User.objects.create(username="a")

    def test_is_participant(self):
        from voteit.meeting.rules import is_participant
        self.assertFalse(is_participant(self.user, self.meeting))
        self.meeting.participants.add(self.user)
        self.meeting.save()
        self.assertTrue(is_participant(self.user, self.meeting))

    def test_is_potential_voter(self):
        from voteit.meeting.rules import is_potential_voter
        self.assertFalse(is_potential_voter(self.user, self.meeting))
        self.meeting.potential_voters.add(self.user)
        self.meeting.save()
        self.assertTrue(is_potential_voter(self.user, self.meeting))
