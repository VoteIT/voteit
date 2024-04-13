from datetime import datetime
from datetime import timedelta

from django.test import TestCase
from django.utils.timezone import now
from django_rq import get_queue
from fakeredis import FakeRedis
from rq.registry import ScheduledJobRegistry

from voteit.invites.jobs import add_to_queue_if_needed
from voteit.invites.jobs import expire_unused_invites
from voteit.invites.jobs import get_expire_job_id
from voteit.invites.models import MeetingInvite
from voteit.invites.workflows import InviteWf
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.workflows import MeetingWf
from voteit.poll.app.er_policies.auto_before_poll import AutoBeforePoll


class ExpireUnusedInvitesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        before = now() - timedelta(days=10)
        cls.meeting: Meeting = Meeting.objects.create(
            er_policy_name=AutoBeforePoll.name, state=MeetingWf.CLOSED, end_time=before
        )
        # cls.user = cls.org.users.create(username="someone")
        cls.inv_old: MeetingInvite = MeetingInvite.objects.create(
            meeting=cls.meeting,
            roles=[ROLE_PARTICIPANT],
            user_data={"email": "a@betahaus.net", "swedish_ssn": "121212-1212"},
            created=before,
        )
        cls.inv_recent: MeetingInvite = MeetingInvite.objects.create(
            meeting=cls.meeting,
            roles=[ROLE_PARTICIPANT],
            user_data={"email": "b@betahaus.net"},
        )

    def test_scheduled_jobs(self):
        connection = FakeRedis()
        queue = get_queue(connection=connection)
        add_to_queue_if_needed(connection=connection)
        registry = ScheduledJobRegistry(queue=queue, connection=queue.connection)
        timestamp = now() + timedelta(days=1)
        self.assertIn(get_expire_job_id(timestamp), registry)
        self.assertIsInstance(
            registry.get_scheduled_time(get_expire_job_id(timestamp)), datetime
        )

    def test_calling_job(self):
        self.assertEqual(1, expire_unused_invites())
        self.inv_old.refresh_from_db()
        self.assertEqual(InviteWf.EXPIRED, self.inv_old.state)
