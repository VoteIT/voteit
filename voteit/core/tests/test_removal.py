from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now
from rest_framework.test import APITestCase
from rq.exceptions import NoSuchJobError

from voteit.core.removal import ACTIVE_MEETING
from voteit.core.removal import INACTIVE_MEETINGS
from voteit.core.removal import NO_ACTIVITY
from voteit.core.removal import ONGOING_POLL
from voteit.core.removal import ORGANISATION_ROLES
from voteit.core.removal import email_removal_requested
from voteit.core.removal import get_removal_report
from voteit.core.removal import get_user_from_abort_token
from voteit.core.removal import make_abort_token
from voteit.core.removal import schedule_removal_email
from voteit.discussion.models import DiscussionPost
from voteit.invites.models import MeetingInvite
from voteit.meeting.models import Meeting
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Vote

User = get_user_model()
VIEWS = "voteit.core.rest_api.views"


class RemovalTestMixin:
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.get(username="participant")
        cls.user.email = "participant@voteit.se"
        cls.user.removal_requested = now()
        cls.user.save()


class AbortTokenTests(RemovalTestMixin, TestCase):
    def test_token(self):
        token = make_abort_token(self.user)
        self.assertEqual(self.user, get_user_from_abort_token(token))

    def test_token_dies_with_the_request(self):
        token = make_abort_token(self.user)
        self.user.removal_requested = now() + timedelta(seconds=1)
        self.user.save()
        self.assertIsNone(get_user_from_abort_token(token))
        self.user.removal_requested = None
        self.user.save()
        self.assertIsNone(get_user_from_abort_token(token))

    def test_bad_token(self):
        self.assertIsNone(get_user_from_abort_token("nope"))


class ScheduleTests(RemovalTestMixin, TestCase):
    @override_settings(REMOVAL_EMAIL_DELAY_MINUTES=7)
    @patch("voteit.core.removal.Job")
    @patch("voteit.core.removal.django_rq.get_queue")
    def test_schedule_replaces_pending(self, get_queue, job_cls):
        queue = MagicMock()
        get_queue.return_value = queue
        schedule_removal_email(self.user, "sv")
        job_cls.fetch.return_value.delete.assert_called_once()
        queue.enqueue_in.assert_called_once()
        args, kwargs = queue.enqueue_in.call_args
        self.assertEqual(timedelta(minutes=7), args[0])
        self.assertEqual(
            (self.user.pk, self.user.removal_requested.isoformat(), "sv"), args[2:]
        )
        self.assertEqual(f"user-removal-email-{self.user.pk}", kwargs["job_id"])

    @patch("voteit.core.removal.Job")
    @patch("voteit.core.removal.django_rq.get_queue")
    def test_schedule_nothing_pending(self, get_queue, job_cls):
        job_cls.fetch.side_effect = NoSuchJobError
        schedule_removal_email(self.user, "sv")
        get_queue.return_value.enqueue_in.assert_called_once()


class EmailJobTests(RemovalTestMixin, TestCase):
    def _run(self):
        return email_removal_requested(
            self.user.pk, self.user.removal_requested.isoformat(), "en"
        )

    def test_sends_abort_link(self):
        self._run()
        self.assertEqual(1, len(mail.outbox))
        msg = mail.outbox[0]
        self.assertEqual(["participant@voteit.se"], msg.to)
        token = make_abort_token(self.user)
        self.assertIn(f"/abort-removal?{urlencode({'token': token})}", msg.body)

    def test_stale_request(self):
        requested = self.user.removal_requested.isoformat()
        self.user.removal_requested = now() + timedelta(seconds=1)
        self.user.save()
        email_removal_requested(self.user.pk, requested, "en")
        self.assertEqual([], mail.outbox)

    def test_aborted(self):
        requested = self.user.removal_requested.isoformat()
        self.user.removal_requested = None
        self.user.save()
        email_removal_requested(self.user.pk, requested, "en")
        self.assertEqual([], mail.outbox)

    def test_no_email(self):
        self.user.email = ""
        self.user.save()
        self._run()
        self.assertEqual([], mail.outbox)


class RemoveInactiveUserTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.organisation = Meeting.objects.get(pk=1).organisation
        cls.user = cls.organisation.users.create(
            username="nobody",
            first_name="Nobody",
            email="nobody@voteit.se",
            removal_requested=now(),
        )

    def _run(self):
        with (
            patch("voteit.core.sessions.end_tracked_sessions") as end_sessions,
            patch("voteit.messaging.close.close_user_connections") as close,
            self.captureOnCommitCallbacks(execute=True),
        ):
            result = email_removal_requested(
                self.user.pk, self.user.removal_requested.isoformat(), "en"
            )
        return result, end_sessions, close

    def test_removed_and_confirmed(self):
        result, end_sessions, close = self._run()
        self.assertEqual(f"Removed user {self.user.pk}", result)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        end_sessions.assert_called_once_with(self.user.pk)
        close.assert_called_once()
        self.assertEqual(self.user.pk, close.call_args.args[0])
        self.assertTrue(close.call_args.kwargs["flush_session"])
        self.assertEqual(1, len(mail.outbox))
        msg = mail.outbox[0]
        self.assertEqual(["nobody@voteit.se"], msg.to)
        self.assertEqual("Your account has been removed", msg.subject)
        self.assertNotIn("abort-removal", msg.body)

    def test_name_falls_back_to_userid(self):
        self.user.first_name = ""
        self.user.userid = "nobody-1"
        self.user.save()
        self._run()
        self.assertIn("Hi nobody-1!", mail.outbox[0].body)

    def test_removed_without_email(self):
        self.user.email = ""
        self.user.save()
        self._run()
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual([], mail.outbox)

    def test_delete_blocked_sends_abort_email(self):
        """A post without an agenda item isn't in the report, but blocks the delete."""
        DiscussionPost.objects.create(author=self.user)
        result, end_sessions, close = self._run()
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        end_sessions.assert_not_called()
        close.assert_not_called()
        self.assertEqual(1, len(mail.outbox))
        self.assertIn("abort-removal", mail.outbox[0].body)

    def test_active_user_kept(self):
        self.user.meeting_roles.create(context_id=1, assigned=["pa"])
        self._run()
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertIn("abort-removal", mail.outbox[0].body)


class RemovalAPITests(RemovalTestMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user.removal_requested = None
        cls.user.save()

    def test_request_schedules_email_in_request_language(self):
        self.client.force_login(self.user)
        with (
            patch(f"{VIEWS}.schedule_removal_email") as schedule,
            self.captureOnCommitCallbacks(execute=True),
            patch(f"{VIEWS}.close_user_connections"),
        ):
            self.client.post(reverse("user-request-removal"), HTTP_ACCEPT_LANGUAGE="sv")
        schedule.assert_called_once()
        self.assertEqual(self.user.pk, schedule.call_args.args[0].pk)
        self.assertEqual("sv", schedule.call_args.args[1])

    def test_request_again_keeps_timer(self):
        self.user.removal_requested = now()
        self.user.save()
        self.client.force_login(self.user)
        with (
            patch(f"{VIEWS}.schedule_removal_email") as schedule,
            self.captureOnCommitCallbacks(execute=True),
            patch(f"{VIEWS}.close_user_connections"),
        ):
            self.client.post(reverse("user-request-removal"))
        schedule.assert_not_called()

    def test_abort_with_token_anonymous(self):
        self.user.removal_requested = now()
        self.user.save()
        token = make_abort_token(self.user)
        with (
            patch(f"{VIEWS}.cancel_removal_email") as cancel,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(reverse("user-abort-removal"), {"token": token})
        self.assertEqual(200, response.status_code)
        self.assertIn("message", response.json())
        cancel.assert_called_once_with(self.user.pk)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.removal_requested)
        # Used up
        response = self.client.post(reverse("user-abort-removal"), {"token": token})
        self.assertEqual(400, response.status_code)

    def test_abort_bad_token(self):
        response = self.client.post(reverse("user-abort-removal"), {"token": "x"})
        self.assertEqual(400, response.status_code)
        self.assertIn("token", response.json())


class RemovalReportTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.participant = User.objects.get(username="participant")
        cls.participant.removal_requested = now()
        cls.participant.save()

    def _set_meeting_state(self, state):
        Meeting.objects.filter(pk=self.meeting.pk).update(state=state)

    def test_no_activity(self):
        user = self.meeting.organisation.users.create(
            username="nobody", removal_requested=now()
        )
        report = get_removal_report(user)
        self.assertEqual(NO_ACTIVITY, report.classification)
        self.assertEqual([], report.meetings)

    def test_org_roles(self):
        manager = User.objects.get(username="org_manager")
        manager.removal_requested = now()
        # Above an ongoing poll
        er = ElectoralRegister.objects.create(meeting=self.meeting)
        er.set_voters_from_dict({manager.pk: 1})
        self.meeting.polls.create(
            method_name="simple", electoral_register=er, state="ongoing"
        )
        report = get_removal_report(manager)
        self.assertEqual(ORGANISATION_ROLES, report.classification)
        self.assertEqual(["org_manager"], report.organisation_roles)

    def test_used_invite_only(self):
        user = self.meeting.organisation.users.create(
            username="invited", removal_requested=now()
        )
        self._set_meeting_state("closed")
        MeetingInvite.objects.create(meeting=self.meeting, used_by=user)
        report = get_removal_report(user)
        self.assertEqual(INACTIVE_MEETINGS, report.classification)
        self.assertEqual(1, len(report.meetings))
        self.assertTrue(report.meetings[0].used_invite)
        self.assertEqual([], report.meetings[0].roles)

    def test_active_meeting(self):
        report = get_removal_report(self.participant)
        self.assertEqual(ACTIVE_MEETING, report.classification)
        meeting = report.meetings[0]
        self.assertEqual(
            (self.meeting.pk, "upcoming", ["pa"]),
            (meeting.pk, meeting.state, meeting.roles),
        )

    def test_closed_meeting(self):
        self._set_meeting_state("closed")
        report = get_removal_report(self.participant)
        self.assertEqual(INACTIVE_MEETINGS, report.classification)

    def test_ongoing_poll(self):
        er = ElectoralRegister.objects.create(meeting=self.meeting)
        er.set_voters_from_dict({self.participant.pk: 1})
        self.meeting.polls.create(
            method_name="simple", electoral_register=er, state="ongoing"
        )
        # Not in this one
        other_er = ElectoralRegister.objects.create(meeting=self.meeting)
        other_er.set_voters_from_dict({1: 1})
        self.meeting.polls.create(
            method_name="simple", electoral_register=other_er, state="ongoing"
        )
        report = get_removal_report(self.participant)
        self.assertEqual(ONGOING_POLL, report.classification)
        self.assertEqual(1, report.meetings[0].ongoing_polls)

    def test_content(self):
        ai = self.meeting.agenda_items.create()
        ai.proposals.create(author=self.participant)
        ai.discussions.create(author=self.participant)
        ai.discussions.create(author=self.participant)
        ai.discussions.create()
        group = self.meeting.groups.create(title="Board")
        group.memberships.create(user=self.participant)
        er = ElectoralRegister.objects.create(meeting=self.meeting)
        er.set_voters_from_dict({self.participant.pk: 1})
        poll = self.meeting.polls.create(
            method_name="simple", electoral_register=er, state="closed"
        )
        Vote.objects.create(user=self.participant, poll=poll, abstain=True)
        with self.assertNumQueries(10):
            report = get_removal_report(self.participant)
        meeting = report.meetings[0]
        self.assertEqual(["Board"], meeting.groups)
        self.assertEqual(1, meeting.votes)
        self.assertEqual(0, meeting.speaker_entries)
        self.assertEqual(1, meeting.proposals)
        self.assertEqual(2, meeting.discussion_posts)

    def test_content_without_roles_still_listed(self):
        """Roles can be gone while the content stays."""
        self._set_meeting_state("archived")
        ai = self.meeting.agenda_items.create()
        user = self.meeting.organisation.users.create(
            username="former", removal_requested=now()
        )
        ai.discussions.create(author=user)
        report = get_removal_report(user)
        self.assertEqual(INACTIVE_MEETINGS, report.classification)
        self.assertEqual(1, report.meetings[0].discussion_posts)

    @override_settings(REMOVAL_WAIT_HOURS=5)
    def test_removable_after(self):
        report = get_removal_report(self.participant)
        self.assertEqual(
            self.participant.removal_requested + timedelta(hours=5),
            report.removable_after,
        )
