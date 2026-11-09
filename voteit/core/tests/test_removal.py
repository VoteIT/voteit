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

from voteit.core.removal import email_removal_requested
from voteit.core.removal import get_user_from_abort_token
from voteit.core.removal import make_abort_token
from voteit.core.removal import schedule_removal_email

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
        ):
            self.client.post(
                reverse("user-request-removal"),
                {"request_removal": True},
                HTTP_ACCEPT_LANGUAGE="sv",
            )
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
        ):
            self.client.post(reverse("user-request-removal"), {"request_removal": True})
        schedule.assert_not_called()

    def test_withdraw_cancels_email(self):
        self.user.removal_requested = now()
        self.user.save()
        self.client.force_login(self.user)
        with (
            patch(f"{VIEWS}.cancel_removal_email") as cancel,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.client.post(
                reverse("user-request-removal"), {"request_removal": False}
            )
        cancel.assert_called_once_with(self.user.pk)

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
