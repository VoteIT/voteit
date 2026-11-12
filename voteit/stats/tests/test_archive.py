import gzip
import json
from datetime import UTC
from datetime import datetime
from io import StringIO
from unittest import mock

from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import InMemoryStorage
from django.core.files.storage import storages
from django.core.management import call_command
from django.test import TestCase
from django.test import override_settings

from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.poll.models import Poll
from voteit.poll.models import Vote

from ..archive import archive_filename
from ..models import MeetingStats
from ..models import OrganisationPeriodStats

User = get_user_model()

JAN = datetime(2024, 1, 15, 12, tzinfo=UTC)
FEB = datetime(2024, 2, 15, 12, tzinfo=UTC)
RECENT = datetime(2026, 10, 1, 12, tzinfo=UTC)
NOW = datetime(2026, 11, 11, 12, tzinfo=UTC)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "auditlog_archive": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
}


@override_settings(STORAGES=STORAGES)
@mock.patch("django.utils.timezone.now", return_value=NOW)
class ArchiveAuditlogTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get()
        cls.org_id = cls.meeting.organisation_id
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.outsider = User.objects.create(
            username="outsider", organisation_id=cls.org_id
        )

    def setUp(self):
        # Fixture loading and setUpTestData may log, start from nothing.
        LogEntry.objects.all().delete()
        # The storage instance outlives a test.
        storage = storages["auditlog_archive"]
        if storage.exists("auditlog"):
            for name in storage.listdir("auditlog")[1]:
                storage.delete(f"auditlog/{name}")

    def log(self, model, object_id, action, changes, timestamp, actor=None, **extra):
        entry = LogEntry.objects.create(
            content_type=ContentType.objects.get_for_model(model),
            object_pk=str(object_id),
            object_id=object_id,
            object_repr="Jane Doe",
            action=action,
            changes=changes,
            actor=actor,
            actor_email=actor and "jane@example.com",
            remote_addr="10.0.0.1",
            additional_data={"o": self.org_id, **extra},
        )
        LogEntry.objects.filter(pk=entry.pk).update(timestamp=timestamp)
        return entry

    def login(self, user, timestamp):
        return self.log(
            User,
            user.pk,
            LogEntry.Action.UPDATE,
            {"last_login": ["2020-01-01 10:00", "2020-01-02 10:00"]},
            timestamp,
        )

    def give_role(self, roles_pk, user_id, meeting_id, timestamp, actor=None):
        self.log(
            MeetingRoles,
            roles_pk,
            LogEntry.Action.CREATE,
            {
                "user": ["None", str(user_id)],
                "context": ["None", str(meeting_id)],
                "assigned": ["None", ""],
            },
            timestamp,
            actor=actor,
            m=meeting_id,
        )
        self.log(
            MeetingRoles,
            roles_pk,
            LogEntry.Action.UPDATE,
            {"assigned": ["[]", "{Participant (pa)}"]},
            timestamp,
            actor=actor,
            m=meeting_id,
        )

    def run_command(self, *args, commit=True) -> str:
        if commit:
            args += ("--commit",)
        out = StringIO()
        call_command("archive_auditlog", *args, stdout=out)
        return out.getvalue()

    def read_archive(self, month: datetime) -> list[dict]:
        with storages["auditlog_archive"].open(archive_filename(month)) as fh:
            return [
                json.loads(line) for line in gzip.decompress(fh.read()).splitlines()
            ]

    def test_nothing_without_commit(self, _now):
        self.login(self.moderator, JAN)
        out = self.run_command(commit=False)
        self.assertIn("2024-01: 1 entries", out)
        self.assertEqual(LogEntry.objects.count(), 1)
        self.assertFalse(OrganisationPeriodStats.objects.exists())
        self.assertFalse(storages["auditlog_archive"].exists(archive_filename(JAN)))

    def test_archives_and_deletes_old_months_only(self, _now):
        self.give_role(500, self.outsider.pk, 999, JAN, actor=self.moderator)
        recent = self.login(self.moderator, RECENT)
        self.run_command()
        self.assertEqual(
            list(LogEntry.objects.values_list("pk", flat=True)), [recent.pk]
        )
        records = self.read_archive(JAN)
        self.assertEqual(
            {
                "ts": "2024-01-15T12:00:00+00:00",
                "action": "update",
                "ct": "meeting.meetingroles",
                "obj": 500,
                "actor": self.moderator.pk,
                "o": self.org_id,
                "m": 999,
                "ai": None,
                "cid": None,
                "facts": {"assigned": [[], ["pa"]]},
            },
            {k: v for k, v in records[1].items() if k != "id"},
        )
        self.assertEqual(
            {
                "user": [None, self.outsider.pk],
                "context": [None, 999],
                "assigned": [None, []],
            },
            records[0]["facts"],
        )

    def test_no_personal_data_in_archive(self, _now):
        self.log(
            User,
            self.outsider.pk,
            LogEntry.Action.UPDATE,
            {"first_name": ["", "Jane"], "email": ["", "jane@example.com"]},
            JAN,
            actor=self.moderator,
        )
        self.run_command()
        with storages["auditlog_archive"].open(archive_filename(JAN)) as fh:
            raw = gzip.decompress(fh.read()).decode()
        self.assertNotIn("Jane", raw)
        self.assertNotIn("example.com", raw)
        self.assertNotIn("10.0.0.1", raw)
        self.assertEqual({}, json.loads(raw)["facts"])

    def test_rerun_is_noop(self, _now):
        self.login(self.moderator, JAN)
        self.run_command()
        out = self.run_command()
        self.assertIn("0 month(s)", out)
        self.assertEqual(OrganisationPeriodStats.objects.count(), 2)

    def test_failed_save_deletes_nothing(self, _now):
        self.login(self.moderator, JAN)
        with mock.patch.object(InMemoryStorage, "save", side_effect=OSError):
            with self.assertRaises(OSError):
                self.run_command()
        self.assertEqual(LogEntry.objects.count(), 1)

    def test_only_whole_months_before_cutoff(self, _now):
        # 18 months before NOW is 2025-05-11, so May 2025 is left whole.
        last_in = self.login(self.moderator, datetime(2025, 4, 30, 23, 59, tzinfo=UTC))
        kept = self.login(self.moderator, datetime(2025, 5, 2, tzinfo=UTC))
        self.run_command()
        self.assertFalse(LogEntry.objects.filter(pk=last_in.pk).exists())
        self.assertEqual([kept.pk], list(LogEntry.objects.values_list("pk", flat=True)))
        self.assertFalse(
            OrganisationPeriodStats.objects.filter(
                start__month=5, period="month"
            ).exists()
        )

    def test_months_argument(self, _now):
        self.login(self.moderator, RECENT)
        self.run_command("--months", "0")
        self.assertFalse(LogEntry.objects.exists())

    def test_period_stats(self, _now):
        self.login(self.moderator, JAN)
        self.login(self.moderator, FEB)
        self.login(self.participant, FEB)
        self.give_role(500, self.outsider.pk, 999, JAN, actor=self.moderator)
        self.run_command()
        stats = {
            (s.period, s.start.month): s for s in OrganisationPeriodStats.objects.all()
        }
        self.assertEqual({("month", 1), ("month", 2), ("year", 1)}, set(stats))
        self.assertEqual(stats["month", 1].unique_logins, 1)
        self.assertEqual(stats["month", 2].unique_logins, 2)
        # Counted once, though January was gone when February was archived.
        self.assertEqual(stats["year", 1].unique_logins, 2)
        self.assertEqual(stats["year", 1].unique_actors, 1)
        self.assertEqual(stats["year", 1].active_meetings, 1)
        self.assertEqual(stats["month", 1].unique_participants, 1)
        self.assertEqual(stats["month", 2].unique_participants, 0)

    def test_keep_entries(self, _now):
        self.login(self.moderator, JAN)
        self.login(self.moderator, FEB)
        self.give_role(500, self.outsider.pk, 999, JAN)
        out = self.run_command("--keep-entries")
        self.assertIn(
            "2024-01: 3 entries archived to auditlog/2024-01.jsonl.gz and kept", out
        )
        self.assertEqual(LogEntry.objects.count(), 4)
        self.assertEqual(len(self.read_archive(JAN)), 3)
        # A rerun recomputes, also counts that went down.
        self.login(self.participant, JAN)
        MeetingStats.objects.update(unique_participants=10)
        self.run_command("--keep-entries")
        self.assertEqual(len(self.read_archive(JAN)), 4)
        stats = {
            (s.period, s.start.month): s.unique_logins
            for s in OrganisationPeriodStats.objects.all()
        }
        self.assertEqual({("month", 1): 2, ("month", 2): 1, ("year", 1): 2}, stats)
        self.assertEqual(
            MeetingStats.objects.get(meeting_id=999).unique_participants, 1
        )
        # And a normal run deletes, without touching the stats.
        OrganisationPeriodStats.objects.update(unique_logins=7)
        self.run_command()
        self.assertFalse(LogEntry.objects.exists())
        self.assertEqual(
            {7},
            set(
                OrganisationPeriodStats.objects.values_list("unique_logins", flat=True)
            ),
        )

    def test_keep_entries_after_delete(self, _now):
        # January and February are gone, the year can't be recomputed.
        self.login(self.moderator, JAN)
        self.login(self.participant, FEB)
        self.give_role(500, self.outsider.pk, 999, JAN)
        self.run_command()
        self.login(self.outsider, datetime(2024, 3, 1, tzinfo=UTC))
        self.give_role(501, self.participant.pk, 999, datetime(2024, 3, 1, tzinfo=UTC))
        MeetingStats.objects.update(unique_participants=10)
        self.run_command("--keep-entries")
        year = OrganisationPeriodStats.objects.get(period="year")
        self.assertEqual(year.unique_logins, 2)
        march = OrganisationPeriodStats.objects.get(period="month", start__month=3)
        self.assertEqual(march.unique_logins, 1)
        # Earlier entries of the meeting are gone, so counts only go up.
        self.assertEqual(
            MeetingStats.objects.get(meeting_id=999).unique_participants, 10
        )

    def test_no_year_stats_for_unfinished_year(self, _now):
        self.login(self.moderator, RECENT)
        self.run_command("--months", "0")
        self.assertEqual(
            ["month"],
            list(OrganisationPeriodStats.objects.values_list("period", flat=True)),
        )

    def test_meeting_stats_for_deleted_meeting(self, _now):
        self.give_role(500, self.outsider.pk, 999, JAN)
        self.give_role(501, self.participant.pk, 999, FEB)
        self.log(
            Meeting, 999, LogEntry.Action.UPDATE, {"title": ["", "Gone"]}, JAN, m=999
        )
        self.run_command()
        stats = MeetingStats.objects.get(meeting_id=999)
        self.assertEqual(stats.unique_participants, 2)
        self.assertEqual(stats.title, "Jane Doe")
        self.assertEqual(stats.first_activity, JAN)
        self.assertEqual(stats.last_activity, FEB)

    def test_meeting_stats_include_current_roles(self, _now):
        # The fixture gives two users "pa" without logging it.
        self.give_role(500, self.outsider.pk, self.meeting.pk, JAN)
        self.run_command()
        stats = MeetingStats.objects.get(meeting_id=self.meeting.pk)
        self.assertEqual(stats.unique_participants, 3)
        self.assertEqual(stats.title, self.meeting.title)

    def test_voters_by_actor(self, _now):
        self.log(
            Poll,
            70,
            LogEntry.Action.CREATE,
            {"meeting": ["None", "999"]},
            JAN,
            m=999,
        )
        vote = {"poll": ["None", "70"], "user": ["None", "1"]}
        # Before the "m" backfill, votes on deleted polls only point out the poll.
        self.log(Vote, 1, LogEntry.Action.CREATE, vote, JAN, actor=self.moderator)
        self.log(
            Vote, 2, LogEntry.Action.CREATE, vote, JAN, actor=self.participant, m=999
        )
        self.log(Vote, 2, LogEntry.Action.UPDATE, vote, JAN, actor=self.outsider, m=999)
        self.run_command()
        stats = MeetingStats.objects.get(meeting_id=999)
        self.assertEqual(stats.unique_voters, 2)
        self.assertEqual(stats.poll_count, 1)

    def test_voters_from_votes(self, _now):
        # Votes weren't logged before late 2026.
        ai = self.meeting.agenda_items.create(meeting=self.meeting)
        poll = Poll.objects.create(
            method_name="simple", agenda_item=ai, meeting=self.meeting
        )
        # Skips save(), which wants an electoral register.
        Vote.objects.bulk_create([Vote(poll=poll, user=self.participant)])
        LogEntry.objects.all().delete()
        self.log(Poll, poll.pk, LogEntry.Action.CREATE, {}, JAN, m=self.meeting.pk)
        self.run_command()
        stats = MeetingStats.objects.get(meeting_id=self.meeting.pk)
        self.assertEqual(stats.unique_voters, 1)
