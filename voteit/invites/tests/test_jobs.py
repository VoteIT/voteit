from datetime import timedelta
from unittest.mock import patch

from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.timezone import now

from voteit.invites.jobs import cleanup_invites
from voteit.invites.jobs import expire_unused_invites
from voteit.invites.models import MeetingInvite
from voteit.invites.statemachines import InviteStateMachine
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.workflows import MeetingWf
from voteit.poll.app.er_policies.auto_before_poll import AutoBeforePoll

User = get_user_model()


class ExpireUnusedInvitesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        before = now() - timedelta(days=40)
        cls.meeting: Meeting = Meeting.objects.create(
            er_policy_name=AutoBeforePoll.name, state=MeetingWf.CLOSED, end_time=before
        )
        cls.inv_old: MeetingInvite = cls.meeting.invites.create(
            roles=[ROLE_PARTICIPANT],
            user_data={"email": "a@betahaus.net", "swedish_ssn": "121212-1212"},
            created=before,
        )
        cls.inv_recent: MeetingInvite = cls.meeting.invites.create(
            roles=[ROLE_PARTICIPANT],
            user_data={"email": "b@betahaus.net"},
        )
        cls.user_one = User.objects.create_user("one")
        cls.user_two = User.objects.create_user("two")
        cls.user_three = User.objects.create_user("three")
        cls.inv_recently_used = cls.meeting.invites.create(
            roles=[ROLE_PARTICIPANT],
            user_data={},
        )
        cls.inv_recently_used.accept(cls.user_one)
        cls.inv_recently_used.save()

        # This will cause the method auto_now to produce a suitable test result
        really_old_ts = now() - timedelta(days=1000)
        with patch("django.utils.timezone.now") as mock_now:
            mock_now.return_value = really_old_ts

            cls.really_old_used = cls.meeting.invites.create(
                roles=[ROLE_PARTICIPANT],
                user_data={},
            )
            cls.really_old_used.accept(cls.user_two)
            cls.really_old_used.save()

            cls.old_revoked = cls.meeting.invites.create(
                roles=[ROLE_PARTICIPANT],
                user_data={},
                state=InviteStateMachine.revoked.id,
            )

    def test_expire_unused_invites(self):
        self.assertEqual(1, expire_unused_invites())
        self.inv_old.refresh_from_db()
        self.assertEqual(InviteStateMachine.expired.id, self.inv_old.state)

    def test_cleanup_unused_invites(self):
        recent_revoked = self.meeting.invites.create(
            roles=[ROLE_PARTICIPANT],
            user_data={},
            state=InviteStateMachine.revoked.id,
        )
        self.assertEqual(
            {"expired_revoked_count": 1, "other_states_count": 1},
            cleanup_invites(),
        )
        recent_revoked.refresh_from_db()
        with self.assertRaises(MeetingInvite.DoesNotExist):
            self.really_old_used.refresh_from_db()
        with self.assertRaises(MeetingInvite.DoesNotExist):
            self.old_revoked.refresh_from_db()

    def test_cleanups_effect_on_logs(self):
        LogEntry.objects.all().delete()
        self.assertEqual(
            {"expired_revoked_count": 1, "other_states_count": 1},
            cleanup_invites(),
        )
        # We're disabling the logs for automated jobs now!
        self.assertEqual(0, LogEntry.objects.count())
