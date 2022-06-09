from django.contrib.auth import get_user_model
from django.test import TestCase
from voteit.poll.exceptions import ElectoralRegisterEmpty
from voteit.poll.exceptions import ElectoralRegisterMissing

User = get_user_model()


class PresenceCheckPolicyTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):

        from voteit.poll.models import Poll
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
        from voteit.poll.app.er_policies.presence_check import PresenceCheckPolicy
        from voteit.presence.models import PresenceCheck

        cls.PresenceCheckPolicy = PresenceCheckPolicy
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.meeting.er_policy_name = PresenceCheckPolicy.name
        cls.meeting.save()
        cls.ai = cls.meeting.agenda_items.create()
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.meeting.add_roles(cls.moderator, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.participant, ROLE_POTENTIAL_VOTER)
        cls.poll = Poll.objects.create(meeting=cls.meeting, method_name="simple")
        cls.poll.proposals.create(agenda_item=cls.ai)
        # Presence check
        cls.presence_check: PresenceCheck = cls.meeting.presence_checks.create()
        cls.presence_check.present_users.add(cls.participant)

    def setUp(self):
        self.meeting.refresh_from_db()
        self.poll.refresh_from_db()
        self.presence_check.refresh_from_db()

    def test_new_er_when_check_closes(self):
        self.presence_check.close()
        self.assertIsNotNone(self.meeting.latest_er)
        self.assertEqual(
            {self.participant},
            set(self.meeting.latest_er.voters.all()),
        )

    def test_starting_poll(self):
        self.poll.upcoming()
        self.assertRaises(
            ElectoralRegisterMissing, self.poll.start_check, exceptions=True
        )

    def test_with_no_present(self):
        self.presence_check.present_users.remove(self.participant)
        self.presence_check.close()
        self.assertEqual(
            set(),
            set(self.meeting.latest_er.voters.all()),
        )
        self.poll.upcoming()
        self.assertRaises(
            ElectoralRegisterEmpty, self.poll.start_check, exceptions=True
        )
