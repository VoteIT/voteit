from importlib import import_module

from auditlog.models import LogEntry
from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from voteit.agenda.models import AgendaItem
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.proposal.models import Proposal

migration = import_module("voteit.stats.migrations.0004_normalise_logentry_changes")
User = get_user_model()


class NormaliseLogEntryChangesTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get()
        cls.org_id = cls.meeting.organisation_id
        cls.jane = User.objects.create(
            username="jane-1", userid="jane", organisation_id=cls.org_id
        )
        cls.ai1 = AgendaItem.objects.create(meeting=cls.meeting, title="One")
        cls.ai2 = AgendaItem.objects.create(meeting=cls.meeting, title="Two")

    def setUp(self):
        LogEntry.objects.all().delete()

    def log(self, model, object_id, action, changes, **extra):
        return LogEntry.objects.create(
            content_type=ContentType.objects.get_for_model(model),
            object_pk=str(object_id),
            object_id=object_id,
            object_repr="",
            action=action,
            changes=changes,
            additional_data={"o": self.org_id, **extra},
        )

    def run_migration(self):
        migration.normalise(apps, None)

    def test_roles_entry(self):
        entry = self.log(
            MeetingRoles,
            9999,
            LogEntry.Action.CREATE,
            {
                "user": ["None", f"Jane Doe (jane) {self.org_id}"],
                "context": ["None", self.meeting.title],
                "assigned": ["None", "('participant', 'moderator')"],
            },
            m=self.meeting.pk,
        )
        self.run_migration()
        entry.refresh_from_db()
        self.assertEqual(
            entry.changes,
            {
                "user": ["None", str(self.jane.pk)],
                "context": ["None", str(self.meeting.pk)],
                "assigned": ["None", "['mo', 'pa']"],
            },
        )

    def test_user_by_username(self):
        entry = self.log(
            MeetingRoles,
            9999,
            LogEntry.Action.DELETE,
            {"user": [f"[jane-1] {self.org_id}", "None"]},
            m=self.meeting.pk,
        )
        self.run_migration()
        entry.refresh_from_db()
        self.assertEqual(entry.changes["user"], [str(self.jane.pk), "None"])

    def test_user_from_existing_object(self):
        roles = MeetingRoles.objects.filter(context=self.meeting).first()
        entry = self.log(
            MeetingRoles,
            roles.pk,
            LogEntry.Action.CREATE,
            {"user": ["None", "Renamed (gone) 1"]},
            m=self.meeting.pk,
        )
        self.run_migration()
        entry.refresh_from_db()
        self.assertEqual(entry.changes["user"], ["None", str(roles.user_id)])

    def test_moved_proposal(self):
        # The old agenda item is only known by title.
        entry = self.log(
            Proposal,
            9999,
            LogEntry.Action.UPDATE,
            {"agenda_item": ["One", "Two"]},
            m=self.meeting.pk,
            ai=self.ai2.pk,
        )
        self.run_migration()
        entry.refresh_from_db()
        self.assertEqual(
            entry.changes["agenda_item"], [str(self.ai1.pk), str(self.ai2.pk)]
        )

    def test_unknown_left_alone(self):
        changes = {"user": ["None", "Gone Away (gone) 1"], "state": ["a", "b"]}
        entry = self.log(MeetingRoles, 9999, LogEntry.Action.CREATE, changes)
        self.run_migration()
        entry.refresh_from_db()
        self.assertEqual(entry.changes, changes)

    def test_meeting_title_in_additional_data(self):
        found = self.log(Proposal, 1, LogEntry.Action.CREATE, {}, m=self.meeting.title)
        gone = self.log(Proposal, 2, LogEntry.Action.CREATE, {}, m="No such meeting")
        self.run_migration()
        found.refresh_from_db()
        gone.refresh_from_db()
        self.assertEqual(
            found.additional_data, {"o": self.org_id, "m": self.meeting.pk}
        )
        self.assertEqual(gone.additional_data, {"o": self.org_id})
