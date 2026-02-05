from datetime import timedelta

from auditlog.context import set_actor
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from ...meeting.models import Meeting
from ...proposal.workflows import ProposalWf
from ..models import HistoryLog

User = get_user_model()


class PopulateJobTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.outsider = User.objects.create(username="outsider")
        cls.participant = User.objects.get(username="participant")
        cls.meeting = Meeting.objects.get()

    @staticmethod
    def _do_job() -> HistoryLog:
        from ..jobs import populate_history_log

        populate_history_log(timezone.now())
        return HistoryLog.objects.get()

    def test_unique(self):
        self._do_job()
        self.assertEqual(HistoryLog.objects.all().count(), 1)
        with self.assertRaises(IntegrityError):
            self._do_job()

    def test_connections(self):
        from envelope.models import Connection

        Connection.objects.create(user=self.moderator, last_action=timezone.now())
        Connection.objects.create(user=self.participant, last_action=timezone.now())
        Connection.objects.create(
            channel_name="other", user=self.moderator, last_action=timezone.now()
        )
        Connection.objects.create(user=self.outsider, last_action=timezone.now())
        entry = self._do_job()

        self.assertEqual(entry.connection_count, 3)
        self.assertEqual(entry.user_online_count, 2)

    def test_action_count(self):
        with set_actor(self.moderator):
            ai = self.meeting.agenda_items.create(title="An agenda item")
            ai.body = "<p>Some content</p>"
            ai.save()
        with set_actor(self.outsider):
            ai.body = "<p>Changed content</p>"
            ai.save()
        entry = self._do_job()
        self.assertEqual(entry.action_count, 2)

    def _mk_speaker_list(self):
        return self.meeting.speaker_systems.create(
            room=self.meeting.rooms.create(title="Room 1")
        ).speaker_lists.create(
            title="Speaker list 1",
            agenda_item=self.meeting.agenda_items.create(title="An agenda item"),
        )

    def test_time_spoken(self):
        sl = self._mk_speaker_list()
        sl.speaker_items.create(seconds=10, started=timezone.now(), user=self.moderator)
        sl.speaker_items.create(
            seconds=20, started=timezone.now(), user=self.participant
        )
        sl.speaker_items.create(
            seconds=30, started=timezone.now(), user=self.outsider
        )  # filtered on user org...
        entry = self._do_job()
        self.assertEqual(entry.spoken_duration.seconds, 30)
        self.assertEqual(entry.speaker_count, 2)
        self.assertEqual(entry.mean_spoken_duration.seconds, 15)

    def test_invitation_use_count(self):
        for user in (self.moderator, self.participant, self.outsider):
            inv = self.meeting.invites.create()
            inv.accept(user=user)
            inv.save()

        entry = self._do_job()
        self.assertEqual(entry.accepted_invitation_count, 2)

    def test_online_duration(self):
        for user in (self.moderator, self.participant, self.outsider):
            user.connections.create(
                online_at=timezone.now() - timedelta(minutes=30),
                last_action=timezone.now(),
            )

        entry = self._do_job()
        self.assertEqual(entry.connection_count, 2)
        self.assertEqual(entry.online_duration.seconds, 3600)
        self.assertEqual(entry.mean_online_duration.seconds, 1800)

    def test_login_count(self):
        for user in (self.participant, self.outsider):
            with set_actor(user):
                user.last_login = timezone.now()
                user.save()
        entry = self._do_job()
        self.assertEqual(entry.login_count, 1)

    def test_proposal_outcomes(self):
        ai = self.meeting.agenda_items.create(title="An agenda item")
        with set_actor(self.moderator):
            for i, states in enumerate(
                (
                    (ProposalWf.VOTING, ProposalWf.APPROVED),
                    (ProposalWf.VOTING, ProposalWf.DENIED),
                    (ProposalWf.VOTING, ProposalWf.DENIED, ProposalWf.UNHANDLED),
                    (ProposalWf.VOTING,),
                ),
                1,
            ):
                for _ in range(i):
                    prop = ai.proposals.create(body="<p>A proposal</p>")
                    for state in states:
                        prop.state = state
                        prop.save()
        entry = self._do_job()
        self.assertDictEqual(
            entry.proposal_outcomes,
            {
                "approved": 1,
                "denied": 2,
                "unhandled": 3,
                "voting": 4,
            },
        )

    def test_action_types(self):
        with set_actor(self.moderator):
            ai = self.meeting.agenda_items.create(title="An agenda item")
            ai.body = "<p>Some content</p>"
            ai.save()
            ai.body = "<p>Other content</p>"
            ai.save()
        entry = self._do_job()
        self.assertDictEqual(
            entry.action_types,
            {"agenda.agendaitem:create": 1, "agenda.agendaitem:update": 2},
        )

    def test_content_types(self):
        ai = self.meeting.agenda_items.create(title="An agenda item")
        ai.proposals.create(body="<p>Some content</p>")
        ai.proposals.create(body="<p>Some other content</p>")
        entry = self._do_job()
        self.assertDictEqual(
            entry.content_types,
            {"meeting.meeting": 1, "agenda.agendaitem": 1, "proposal.proposal": 2},
        )
