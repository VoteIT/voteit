from django.contrib.auth import get_user_model
from django.test import TestCase
from envelope.messages.errors import UnauthorizedError
from envelope.messages.errors import ValidationErrorMsg


User = get_user_model()


class ChangePresenceTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.presence.models import PresenceSystem
        from voteit.presence.models import PresenceCheck
        from voteit.meeting.models import Meeting

        cls.outsider = User.objects.create(username="outsider")
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.participant = User.objects.get(username="participant")
        cls.moderator = User.objects.get(username="moderator")
        cls.system = PresenceSystem.objects.create(meeting=cls.meeting)
        cls.check = PresenceCheck.objects.create(meeting=cls.meeting)

    @property
    def _cut(self):
        from voteit.presence.messages import ChangePresence

        return ChangePresence

    def _mk_one(self, *, user, check, present, presence_user=None):
        return self._cut(
            mm={"user_pk": user.pk, "consumer_name": "abc"},
            presence_check=check.pk,
            present=present,
            user=presence_user,
        )

    def test_add(self):
        self.assertFalse(self.check.present_users.count())
        msg = self._mk_one(user=self.participant, check=self.check, present=True)
        msg.run_job()
        self.assertTrue(self.check.present_users.count())
        # Make sure duplicate doesn't kill it
        msg.run_job()

    def test_add_closed_check(self):
        self.check.close()
        self.check.save()
        msg = self._mk_one(user=self.participant, check=self.check, present=True)
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_add_not_participant(self):
        msg = self._mk_one(user=self.outsider, check=self.check, present=True)
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_user_add_other_user(self):
        msg = self._mk_one(
            user=self.participant,
            check=self.check,
            present=True,
            presence_user=self.moderator,
        )
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_moderator_add_other_user(self):
        msg = self._mk_one(
            user=self.moderator,
            check=self.check,
            present=True,
            presence_user=self.participant,
        )
        msg.run_job()
        self.assertIn(self.participant, self.check.present_users.all())
        self.assertNotIn(self.moderator, self.check.present_users.all())

    def test_moderator_add_outsider(self):
        msg = self._mk_one(
            user=self.moderator,
            check=self.check,
            present=True,
            presence_user=self.outsider,
        )
        self.assertRaises(ValidationErrorMsg, msg.run_job)

    def test_moderator_add_user_that_doest_exist(self):
        msg = self._mk_one(
            user=self.moderator,
            check=self.check,
            present=True,
            presence_user=-1,
        )
        self.assertRaises(ValidationErrorMsg, msg.run_job)

    def test_moderator_add_closed(self):
        self.check.close()
        self.check.save()
        msg = self._mk_one(user=self.moderator, check=self.check, present=True)
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_delete(self):
        self.check.presences.create(user=self.participant)
        # self.assertTrue(self.check.present_users.count())
        msg = self._mk_one(user=self.participant, check=self.check, present=False)
        msg.run_job()
        self.assertFalse(self.check.presences.count())

    def test_delete_doest_exist(self):
        # No errors here
        msg = self._mk_one(user=self.participant, check=self.check, present=False)
        msg.run_job()
        self.assertFalse(self.check.presences.count())

    def test_delete_closed_check(self):
        self.check.close()
        self.check.save()
        msg = self._mk_one(user=self.participant, check=self.check, present=False)
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_delete_moderator_closed_check(self):
        self.check.presences.create(user=self.participant)
        self.check.close()
        self.check.save()
        msg = self._mk_one(
            user=self.moderator,
            check=self.check,
            present=False,
            presence_user=self.participant,
        )
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_delete_moderator(self):
        self.check.presences.create(user=self.participant)
        msg = self._mk_one(
            user=self.moderator,
            check=self.check,
            present=False,
            presence_user=self.participant,
        )
        msg.run_job()
        self.assertFalse(self.check.presences.count())

    def test_delete_moderator_nonexisting_outsider(self):
        self.check.presences.create(user=self.outsider)
        msg = self._mk_one(
            user=self.moderator,
            check=self.check,
            present=False,
            presence_user=self.outsider,
        )
        msg.run_job()
        self.assertFalse(self.check.presences.count())

    def test_delete_moderator_existing_outsider(self):
        self.check.presences.create(user=self.outsider)
        msg = self._mk_one(
            user=self.moderator,
            check=self.check,
            present=False,
            presence_user=self.outsider,
        )
        msg.run_job()
        self.assertFalse(self.check.presences.count())
