import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.test import override_settings

from voteit.core.anonymise import anonymise_user
from voteit.invites.models import MeetingInvite
from voteit.meeting.models import Meeting
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Vote

User = get_user_model()


class AnonymiseUserTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        # Has meeting roles and a social auth in the fixture
        cls.user = User.objects.get(username="moderator")
        cls.user.identity_id = "abc"
        cls.user.img_url = "https://example.com/me.png"
        cls.user.is_staff = True
        cls.user.save()

    def _run(self):
        with (
            patch("voteit.core.sessions.end_tracked_sessions") as end_sessions,
            patch("voteit.messaging.close.close_user_connections") as close,
            self.captureOnCommitCallbacks(execute=True),
        ):
            anonymise_user(self.user)
        self.user.refresh_from_db()
        return end_sessions, close

    def test_blanks_user_row(self):
        pk = self.user.pk
        self._run()
        user = self.user
        self.assertEqual(pk, user.pk)
        self.assertEqual(
            ("", "", "", f"removed-{pk}", None, None, None),
            (
                user.first_name,
                user.last_name,
                user.email,
                user.username,
                user.userid,
                user.identity_id,
                user.img_url,
            ),
        )
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.has_usable_password())
        self.assertIsNotNone(user.anonymised)

    def test_keeps_references(self):
        self._run()
        self.assertTrue(self.meeting.has_roles(self.user, "mo"))
        self.assertEqual(self.user.organisation_id, 1)

    def test_removes_login_methods(self):
        self.assertTrue(self.user.social_auth.exists())
        self._run()
        self.assertFalse(self.user.social_auth.exists())

    def test_ends_access(self):
        end_sessions, close = self._run()
        end_sessions.assert_called_once_with(self.user.pk)
        self.assertEqual(self.user.pk, close.call_args.args[0])
        self.assertTrue(close.call_args.kwargs["flush_session"])

    def test_clears_used_invite_data(self):
        used = MeetingInvite.objects.create(
            meeting=self.meeting,
            used_by=self.user,
            state="accepted",
            user_data={"email": "moderator@voteit.se"},
        )
        other = MeetingInvite.objects.create(
            meeting=self.meeting, user_data={"email": "someone@voteit.se"}
        )
        self._run()
        used.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual({}, used.user_data)
        self.assertEqual(self.user, used.used_by)
        self.assertEqual({"email": "someone@voteit.se"}, other.user_data)

    def test_deletes_image_after_commit(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.user.image.save("me.png", ContentFile(b"x"), save=True)
                storage = self.user.image.storage
                name = self.user.image.name
                self.assertTrue(storage.exists(name))
                self._run()
                self.assertFalse(storage.exists(name))
                self.assertFalse(self.user.image)

    def test_deletes_votes(self):
        er = ElectoralRegister.objects.create(meeting=self.meeting)
        er.set_voters_from_dict({self.user.pk: 1})
        closed = self.meeting.polls.create(
            method_name="simple", electoral_register=er, state="closed"
        )
        ongoing = self.meeting.polls.create(
            method_name="simple", electoral_register=er, state="ongoing"
        )
        for poll in (closed, ongoing):
            Vote.objects.create(user=self.user, poll=poll, abstain=True)
        with patch("voteit.poll.jobs.schedule_poll_status_publish") as publish:
            self._run()
        self.assertFalse(Vote.objects.filter(user=self.user).exists())
        publish.assert_called_once_with(ongoing.pk)
