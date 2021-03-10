from django.contrib.auth import get_user_model
from django.test import TestCase
from voteit.messaging.errors import UnauthorizedError, ValidationErrorMsg


User = get_user_model()


class _PresenceFixture:
    def fixture(self):
        from voteit.presence.models import PresenceSystem
        from voteit.presence.models import PresenceCheck
        from voteit.meeting.models import Meeting

        self.user = User.objects.create(username="creeper")
        self.meeting = Meeting.objects.create()
        self.meeting.add_roles(self.user, "participant")
        self.system = PresenceSystem.objects.create(meeting=self.meeting)
        self.check = PresenceCheck.objects.create(presence_system=self.system)


class AddPresenceTests(TestCase, _PresenceFixture):
    def setUp(self):
        self.fixture()

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
    def setUp(self):
        from voteit.presence.models import Presence

        self.fixture()
        self.presence = Presence.objects.create(
            user=self.user, presence_check=self.check
        )

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
    def setUp(self):
        self.fixture()
        self.moderator = User.objects.create(username="moderator")
        self.meeting.add_roles(self.moderator, "moderator")

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
    def setUp(self):
        from voteit.presence.models import Presence

        self.fixture()
        self.presence = Presence.objects.create(
            user=self.user, presence_check=self.check
        )
        self.moderator = User.objects.create(username="moderator")
        self.meeting.add_roles(self.moderator, "moderator")

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
