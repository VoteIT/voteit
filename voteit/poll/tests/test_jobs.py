from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from redis.exceptions import ConnectionError

from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.app.er_policies.auto_always import AutoAlways
from voteit.poll.jobs import publish_poll_status
from voteit.poll.jobs import schedule_poll_status_publish
from voteit.poll.messages import PollStatus

User = get_user_model()


class PublishPollStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create(
            er_policy_name=AutoAlways.name, state="ongoing"
        )
        cls.user = User.objects.create(username="user")
        cls.meeting.add_roles(cls.user, ROLE_PARTICIPANT, ROLE_POTENTIAL_VOTER)
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop = cls.ai.proposals.create()
        cls.poll = cls.meeting.polls.create(method_name="simple")
        cls.poll.proposals.add(cls.prop)
        cls.poll.ongoing(force=True)
        cls.poll.save()

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_publishes_current_count(self, mock_publish):
        self.poll.votes.create(user=self.user, vote="yes")

        publish_poll_status(self.poll.pk)

        mock_publish.assert_called_once()
        msg = mock_publish.call_args.args[0]
        self.assertIsInstance(msg, PollStatus)
        self.assertEqual(1, msg.payload.voted)
        self.assertEqual(1, msg.payload.total)

    def test_missing_poll_is_noop(self):
        poll_pk = self.poll.pk
        # Patch around the call only: deleting the poll publishes a
        # PollDeleted to this same channel, which is not what is under test.
        self.poll.delete()

        with patch.object(ParticipantsChannel, "sync_publish") as mock_publish:
            publish_poll_status(poll_pk)

        mock_publish.assert_not_called()

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_missing_electoral_register_is_noop(self, mock_publish):
        self.poll.electoral_register = None
        self.poll.save()

        publish_poll_status(self.poll.pk)

        mock_publish.assert_not_called()


class SchedulePollStatusPublishTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create(
            er_policy_name=AutoAlways.name, state="ongoing"
        )
        cls.ai = cls.meeting.agenda_items.create()
        cls.poll = cls.meeting.polls.create(method_name="simple")

    @patch("voteit.poll.jobs.Job")
    @patch("voteit.poll.jobs.django_rq.get_queue")
    def test_schedules_when_none_pending(self, mock_get_queue, mock_job):
        mock_job.exists.return_value = False
        mock_queue = MagicMock()
        mock_get_queue.return_value = mock_queue

        schedule_poll_status_publish(self.poll.pk)

        mock_queue.enqueue_in.assert_called_once()
        args, kwargs = mock_queue.enqueue_in.call_args
        self.assertEqual(publish_poll_status, args[1])
        self.assertEqual(self.poll.pk, args[2])
        self.assertEqual(f"poll-status-{self.poll.pk}", kwargs["job_id"])

    @override_settings(POLL_STATUS_THROTTLE_SECONDS=7)
    @patch("voteit.poll.jobs.Job")
    @patch("voteit.poll.jobs.django_rq.get_queue")
    def test_uses_throttle_from_settings(self, mock_get_queue, mock_job):
        mock_job.exists.return_value = False
        mock_queue = MagicMock()
        mock_get_queue.return_value = mock_queue

        schedule_poll_status_publish(self.poll.pk)

        args, kwargs = mock_queue.enqueue_in.call_args
        self.assertEqual(timedelta(seconds=7), args[0])

    @patch("voteit.poll.jobs.Job")
    @patch("voteit.poll.jobs.django_rq.get_queue")
    def test_skips_when_already_pending(self, mock_get_queue, mock_job):
        mock_job.exists.return_value = True
        mock_queue = MagicMock()
        mock_get_queue.return_value = mock_queue

        schedule_poll_status_publish(self.poll.pk)

        mock_queue.enqueue_in.assert_not_called()

    @patch("voteit.poll.jobs.publish_poll_status")
    @patch("voteit.poll.jobs.Job")
    @patch("voteit.poll.jobs.django_rq.get_queue")
    def test_falls_back_to_sync_publish_when_redis_unreachable(
        self, mock_get_queue, mock_job, mock_publish
    ):
        mock_job.exists.return_value = False
        mock_queue = MagicMock()
        mock_queue.enqueue_in.side_effect = ConnectionError("down")
        mock_get_queue.return_value = mock_queue

        schedule_poll_status_publish(self.poll.pk)

        mock_publish.assert_called_once_with(self.poll.pk)
