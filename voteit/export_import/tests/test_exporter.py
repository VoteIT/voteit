from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from pydantic import ValidationError

from voteit.agenda.workflows import AgendaItemWf
from voteit.export_import.utils import verify_signature
from voteit.meeting.models import Meeting
from voteit.proposal.workflows import ProposalWf
from voteit.export_import import schemas

User = get_user_model()


@override_settings(EXPORT_SECRET_KEY="abcdefghijk")
class ExporterTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture", "full_ai_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)

    @property
    def _cut(self):
        from voteit.export_import.exporter import Exporter

        return Exporter

    def test_defaults(self):
        exporter = self._cut(self.meeting)
        exporter()
        self.assertEqual("Testfixture meeting", exporter.data.meta.title)
        self.assertEqual(3, len(exporter.data.agenda_items))
        self.assertEqual(AgendaItemWf.UPCOMING, exporter.data.agenda_items[0].state)
        self.assertTrue(exporter.data.agenda_items[0].discussions)
        self.assertTrue(exporter.data.agenda_items[0].proposals)
        self.assertEqual(
            ProposalWf.APPROVED, exporter.data.agenda_items[0].proposals[0].state
        )
        self.assertEqual(
            "loeksas-1", exporter.data.agenda_items[0].proposals[0].prop_id
        )
        self.assertTrue(exporter.data.groups)
        self.assertEqual(
            schemas.UserData(email="participant@voteit.se", pk=2),
            exporter.data.agenda_items[0].discussions[0].author,
        )
        self.assertEqual("The Hellos", exporter.data.groups[0].title)
        self.assertEqual(
            "the-hellos", exporter.data.agenda_items[0].discussions[0].meeting_group
        )

    def test_bad_kwargs(self):
        exporter = self._cut(self.meeting, woho=1)
        with self.assertRaises(ValidationError):
            exporter()

    def test_no_discussions(self):
        exporter = self._cut(self.meeting, include_discussions=False)
        exporter()
        self.assertFalse(exporter.data.agenda_items[0].discussions)

    def test_no_groups(self):
        exporter = self._cut(
            self.meeting, include_groups=False, clear_group_authors=True
        )
        exporter()
        self.assertFalse(exporter.data.groups)
        self.assertFalse(exporter.data.agenda_items[0].discussions[0].meeting_group)

    def test_no_authors(self):
        exporter = self._cut(self.meeting, clear_authors=True)
        exporter()
        self.assertFalse(exporter.data.agenda_items[0].discussions[0].author)

    def test_no_proposals(self):
        exporter = self._cut(self.meeting, include_proposals=False)
        exporter()
        self.assertFalse(exporter.data.agenda_items[0].proposals)

    def test_clear_ai_states(self):
        exporter = self._cut(self.meeting, clear_ai_states=True)
        exporter()
        self.assertEqual(None, exporter.data.agenda_items[0].state)

    def test_clear_proposal_states(self):
        exporter = self._cut(self.meeting, clear_proposal_states=True)
        exporter()
        self.assertEqual(None, exporter.data.agenda_items[0].proposals[0].state)

    def test_clear_proposal_id(self):
        exporter = self._cut(self.meeting, clear_proposal_id=True)
        exporter()
        self.assertEqual(None, exporter.data.agenda_items[0].proposals[0].prop_id)
