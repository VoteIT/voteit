from django.contrib.auth import get_user_model
from django.test import TestCase
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

User = get_user_model()


class AutoAlwaysTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import Poll
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
        from voteit.poll.app.er_policies.auto_always import AutoAlways
        from voteit.poll.models import ElectoralRegister

        cls.AutoAlways = AutoAlways
        cls.ElectoralRegister = ElectoralRegister

        cls.meeting = Meeting.objects.create(er_policy_name=AutoAlways.name)
        cls.user1 = User.objects.create(username="one")
        cls.user2 = User.objects.create(username="two")
        cls.meeting.add_roles(cls.user1, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.user2, ROLE_POTENTIAL_VOTER)
        cls.poll = Poll.objects.create(meeting=cls.meeting, method_name="simple")
        cls.poll.proposals.create()

    def setUp(self):
        self.poll.refresh_from_db()

    def test_new_er_on_upcoming(self):
        self.poll.upcoming()
        self.assertIsInstance(self.poll.electoral_register, self.ElectoralRegister)
        self.assertEqual(
            {self.user1, self.user2}, set(self.poll.electoral_register.voters.all())
        )

    def test_new_er_for_started_poll_when_roles_removed(self):
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.save()
        self.assertEqual(
            self.poll.initial_electoral_register, self.poll.electoral_register
        )
        self.meeting.remove_roles(self.user1, ROLE_POTENTIAL_VOTER)
        self.poll.refresh_from_db(
            fields=("initial_electoral_register", "electoral_register")
        )
        self.assertNotEqual(
            self.poll.initial_electoral_register, self.poll.electoral_register
        )

    def test_new_er_for_started_poll_when_roles_added(self):
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.save()
        initial_er = self.poll.initial_electoral_register
        first_er = self.poll.electoral_register
        self.assertEqual(initial_er, first_er)
        self.meeting.remove_roles(self.user1, ROLE_POTENTIAL_VOTER)
        self.poll.refresh_from_db(
            fields=("initial_electoral_register", "electoral_register")
        )
        self.assertNotEqual(initial_er, self.poll.electoral_register)
        second_er = self.poll.electoral_register
        self.meeting.add_roles(self.user1, ROLE_POTENTIAL_VOTER)
        self.poll.refresh_from_db(
            fields=("initial_electoral_register", "electoral_register")
        )
        self.assertNotEqual(second_er, self.poll.electoral_register)
        # But adding the same role has no effect
        third_er = self.poll.electoral_register
        self.meeting.add_roles(self.user1, ROLE_POTENTIAL_VOTER)
        self.poll.refresh_from_db(
            fields=("initial_electoral_register", "electoral_register")
        )
        self.assertEqual(third_er, self.poll.electoral_register)

    def test_cleanup_unused_ers(self):
        one = self.meeting.electoral_registers.create(source=self.AutoAlways.name)
        self.assertEqual(2, self.meeting.electoral_registers.count())
        self.meeting.remove_roles(self.user2, ROLE_POTENTIAL_VOTER)
        # First one deleted
        self.assertEqual(1, self.meeting.electoral_registers.count())
        self.assertNotIn(one, self.meeting.electoral_registers.all())
        # We'll keep this er though
        two = self.meeting.get_latest_er()
        self.poll.upcoming()
        self.poll.save()
        self.assertEqual(two, self.poll.electoral_register)
        self.poll.state = "closed"
        self.poll.save()
        self.meeting.add_roles(self.user2, ROLE_POTENTIAL_VOTER)
        self.assertNotEqual(two, self.meeting.get_latest_er())
        self.assertEqual(two, self.poll.electoral_register)
        # So one more kept
        self.assertEqual(2, self.meeting.electoral_registers.count())
