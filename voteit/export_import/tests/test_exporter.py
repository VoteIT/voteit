from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from pydantic import ValidationError

from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup

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
        self.assertEqual(
            AgendaItemStateMachine.upcoming.value, exporter.data.agenda_items[0].state
        )
        self.assertTrue(exporter.data.agenda_items[0].discussions)
        self.assertTrue(exporter.data.agenda_items[0].proposals)
        self.assertEqual("approved", exporter.data.agenda_items[0].proposals[0].state)
        self.assertEqual(
            "loeksas-1", exporter.data.agenda_items[0].proposals[0].prop_id
        )
        self.assertTrue(exporter.data.groups)
        self.assertEqual("The Hellos", exporter.data.groups[0].title)
        self.assertEqual(
            "the-hellos", exporter.data.agenda_items[0].discussions[0].meeting_group
        )
        self.assertEqual(2, len(exporter.data.reaction_buttons))
        self.assertEqual("Gilla", exporter.data.reaction_buttons[0].title)
        self.assertEqual(
            "Valberedningens förslag", exporter.data.reaction_buttons[1].title
        )
        self.assertSetEqual(
            {
                "title",
                "vote_template",
                "active",
                "icon",
                "list_roles",
                "flag_mode",
                "on_presentation",
                "target",
                "order",
                "on_vote",
                "color",
                "description",
                "change_roles",
                "allowed_models",
                "reactions",
            },
            set(exporter.data.reaction_buttons[1].dict()),
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

    def test_no_buttons(self):
        exporter = self._cut(self.meeting, include_buttons=False)
        exporter()
        self.assertFalse(exporter.data.reaction_buttons)

    def test_with_reactions(self):
        exporter = self._cut(self.meeting, include_reactions=True)
        exporter()
        # Button 1
        self.assertEqual("Gilla", exporter.data.reaction_buttons[0].title)
        self.assertEqual(3, len(exporter.data.reaction_buttons[0].reactions))
        self.assertDictEqual(
            {
                "agenda_item_id": "_1",
                "content_type": ["proposal", "proposal"],
                "object_id": "_2",
                "username": "participant",
            },
            exporter.data.reaction_buttons[0].reactions[0].dict(),
        )
        self.assertDictEqual(
            {
                "agenda_item_id": "_1",
                "content_type": ["proposal", "proposal"],
                "object_id": "_2",
                "username": "moderator",
            },
            exporter.data.reaction_buttons[0].reactions[1].dict(),
        )
        self.assertDictEqual(
            {
                "agenda_item_id": "_1",
                "content_type": ["discussion", "discussionpost"],
                "object_id": "_1",
                "username": "moderator",
            },
            exporter.data.reaction_buttons[0].reactions[2].dict(),
        )
        # Button 2
        self.assertEqual(
            "Valberedningens förslag", exporter.data.reaction_buttons[1].title
        )
        self.assertEqual(1, len(exporter.data.reaction_buttons[1].reactions))

    def test_with_reactions_no_discussions(self):
        exporter = self._cut(
            self.meeting, include_reactions=True, include_discussions=False
        )
        exporter()
        # Button 1
        self.assertEqual(2, len(exporter.data.reaction_buttons[0].reactions))

    def test_with_reactions_no_proposals(self):
        exporter = self._cut(
            self.meeting, include_reactions=True, include_proposals=False
        )
        exporter()
        # Button 1
        self.assertEqual(1, len(exporter.data.reaction_buttons[0].reactions))

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

    def test_group_with_delegate_to(self):
        the_hellos = self.meeting.groups.get(groupid="the-hellos")
        delegating = MeetingGroup.objects.create(
            meeting=self.meeting,
            title="Delegating group",
            delegate_to=the_hellos,
        )
        exporter = self._cut(self.meeting)
        exporter()
        delegating_data = next(
            g for g in exporter.data.groups if g.groupid == delegating.groupid
        )
        self.assertEqual("the-hellos", delegating_data.delegate_to)
