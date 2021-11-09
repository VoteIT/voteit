from django.contrib.auth import get_user_model
from django.test import TestCase
from voteit.messaging.errors import UnauthorizedError, ValidationErrorMsg


User = get_user_model()


class _PresenceFixture:
    @classmethod
    def fixture(cls):
        from voteit.presence.models import PresenceSystem
        from voteit.presence.models import PresenceCheck
        from voteit.meeting.models import Meeting

        cls.user = User.objects.create(username="creeper")
        cls.meeting = Meeting.objects.create()
        cls.meeting.add_roles(cls.user, "participant")
        cls.system = PresenceSystem.objects.create(meeting=cls.meeting)
        cls.check = PresenceCheck.objects.create(meeting=cls.meeting)


class AddPresenceTests(TestCase, _PresenceFixture):
    @classmethod
    def setUpTestData(cls):
        cls.fixture()

    @property
    def _cut(self):
        from voteit.presence.messages import AddPresence

        return AddPresence

    def _mk_one(self):
        return self._cut(
            {"user_pk": self.user.pk, "consumer_name": "abc"},
            presence_check=self.check.pk,
        )

    def test_add(self):
        self.assertFalse(self.check.present_users.count())
        msg = self._mk_one()
        msg.run_job()
        self.assertTrue(self.check.present_users.count())

    def test_add_closed_check(self):
        self.check.close()
        self.check.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_add_not_participant(self):
        self.meeting.remove_roles(self.user, "participant")
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)


class RemovePresenceTests(TestCase, _PresenceFixture):
    @classmethod
    def setUpTestData(cls):
        from voteit.presence.models import Presence

        cls.fixture()
        cls.presence = Presence.objects.create(user=cls.user, presence_check=cls.check)

    @property
    def _cut(self):
        from voteit.presence.messages import DeletePresence

        return DeletePresence

    def _mk_one(self):
        return self._cut(
            {"user_pk": self.user.pk, "consumer_name": "abc"}, pk=self.presence.pk
        )

    def test_delete(self):
        self.assertTrue(self.check.present_users.count())
        msg = self._mk_one()
        msg.run_job()
        self.assertFalse(self.check.present_users.count())

    def test_delete_closed_check(self):
        self.check.close()
        self.check.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_delete_other_user(self):
        other = User.objects.create(username="another")
        self.meeting.add_roles(other, "participant")
        msg = self._mk_one()
        msg.mm.user_pk = other.pk
        self.assertRaises(UnauthorizedError, msg.run_job)


class AddUserPresenceTests(TestCase, _PresenceFixture):
    @classmethod
    def setUpTestData(cls):
        cls.fixture()
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, "moderator")

    @property
    def _cut(self):
        from voteit.presence.messages import AddUserPresence

        return AddUserPresence

    def _mk_one(self):
        return self._cut(
            {"user_pk": self.moderator.pk, "consumer_name": "abc"},
            presence_check=self.check.pk,
            userid=self.user.pk,
        )

    def test_add(self):
        self.assertFalse(self.check.present_users.count())
        msg = self._mk_one()
        msg.run_job()
        self.assertTrue(self.check.present_users.count())

    def test_add_closed_check(self):
        self.check.close()
        self.check.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_add_not_participant(self):
        self.meeting.remove_roles(self.user, "participant")
        msg = self._mk_one()
        self.assertRaises(ValidationErrorMsg, msg.run_job)

    def test_add_regular_user(self):
        self.meeting.remove_roles(self.moderator, "moderator")
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_add_non_existing_userid(self):
        msg = self._mk_one()
        msg.data.userid = -1
        self.assertRaises(ValidationErrorMsg, msg.run_job)


class RemoveUserPresenceTests(TestCase, _PresenceFixture):
    @classmethod
    def setUpTestData(cls):
        from voteit.presence.models import Presence

        cls.fixture()
        cls.presence = Presence.objects.create(user=cls.user, presence_check=cls.check)
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, "moderator")

    @property
    def _cut(self):
        from voteit.presence.messages import DeleteUserPresence

        return DeleteUserPresence

    def _mk_one(self):
        return self._cut(
            {"user_pk": self.moderator.pk, "consumer_name": "abc"},
            pk=self.presence.pk,
            userid=self.user.pk,
        )

    def test_delete(self):
        self.assertTrue(self.check.present_users.count())
        msg = self._mk_one()
        msg.run_job()
        self.assertFalse(self.check.present_users.count())

    def test_delete_closed_check(self):
        self.check.close()
        self.check.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_delete_regular_user(self):
        self.meeting.remove_roles(self.moderator, "moderator")
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)
