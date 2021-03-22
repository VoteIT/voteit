from django.contrib.auth import get_user_model
from django.test import TestCase
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

User = get_user_model()


class AutoAlwaysTests(TestCase):
    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

        self.meeting = Meeting.objects.create(er_policy_name=self._cut.name)
        self.user1 = User.objects.create(username="one")
        self.user2 = User.objects.create(username="two")
        self.meeting.add_roles(self.user1, ROLE_POTENTIAL_VOTER)
        self.meeting.add_roles(self.user2, ROLE_POTENTIAL_VOTER)
        self.poll = Poll.objects.create(meeting=self.meeting, method_name="simple")
        self.poll.proposals.create()

    @property
    def _cut(self):
        from voteit.poll.app.er_policys import AutoAlways

        return AutoAlways

    @property
    def ElectoralRegister(self):
        from voteit.poll.models import ElectoralRegister

        return ElectoralRegister

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
