from django.test import TestCase
from pydantic import ValidationError

from voteit.export_import.utils import direct_clone
from voteit.meeting.models import Meeting


class UtilsTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture", "full_ai_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.org = cls.meeting.organisation
        cls.new_meeting = cls.org.meetings.create()
        cls.btn = cls.meeting.reaction_buttons.get(pk=1)

    def test_direct_clone(self):
        importer = direct_clone(
            source=self.meeting,
            target=self.new_meeting,
            commit=True,
            include_reactions=True,
        )
        self.assertEqual(
            {
                "agenda_items": 3,
                "buttons": 2,
                "diff_proposals": 1,
                "discussion_posts": 2,
                "groups": 1,
                "proposals": 4,
                "reactions": 4,
                "text_documents": 1,
                "groups_reused": 0,
                "buttons_reused": 0,
            },
            importer.stats().dict(),
        )
        self.assertSetEqual(
            self.meeting.agenda_items.values_list("title", flat=True),
            self.new_meeting.agenda_items.values_list("title", flat=True),
        )

    def test_direct_clone_no_commit(self):
        importer = direct_clone(
            source=self.meeting,
            target=self.new_meeting,
            commit=False,
            include_reactions=True,
        )
        self.assertEqual(
            {
                "agenda_items": 3,
                "buttons": 2,
                "diff_proposals": 1,
                "discussion_posts": 2,
                "groups": 1,
                "proposals": 4,
                "reactions": 4,
                "text_documents": 1,
                "groups_reused": 0,
                "buttons_reused": 0,
            },
            importer.stats().dict(),
        )
        self.assertSetEqual(
            self.meeting.agenda_items.none(),
            self.new_meeting.agenda_items.values_list("title", flat=True),
        )

    def test_direct_clone_no_discussions(self):
        importer = direct_clone(
            source=self.meeting,
            target=self.new_meeting,
            commit=False,
            include_reactions=True,
            include_discussions=False,
        )
        self.assertEqual(
            {
                "agenda_items": 3,
                "buttons": 2,
                "diff_proposals": 1,
                "discussion_posts": 0,
                "groups": 1,
                "proposals": 4,
                "reactions": 3,
                "text_documents": 1,
                "groups_reused": 0,
                "buttons_reused": 0,
            },
            importer.stats().dict(),
        )

    def test_direct_clone_bad_options(self):
        with self.assertRaises(ValidationError) as cm:
            direct_clone(
                source=self.meeting,
                target=self.new_meeting,
                include_reactions=True,
                include_buttons=False,
            )
        self.assertEqual(
            [
                {
                    "loc": ("include_reactions",),
                    "msg": "Buttons are needed to set reactions - change 'include_buttons'",
                    "type": "value_error",
                }
            ],
            cm.exception.errors(),
        )

    def test_clone_flags(self):
        self.btn.flag = True
        self.btn.save()
        importer = direct_clone(
            source=self.meeting,
            target=self.new_meeting,
            commit=True,
            include_reactions=True,
        )
        self.assertEqual(
            {
                "agenda_items": 3,
                "buttons": 2,
                "diff_proposals": 1,
                "discussion_posts": 2,
                "groups": 1,
                "proposals": 4,
                "reactions": 4,
                "text_documents": 1,
                "groups_reused": 0,
                "buttons_reused": 0,
            },
            importer.stats().dict(),
        )
        # And once again
        importer = direct_clone(
            source=self.meeting,
            target=self.new_meeting,
            commit=True,
            include_reactions=True,
        )
        self.assertEqual(
            {
                "agenda_items": 3,
                "buttons": 2,
                "diff_proposals": 1,
                "discussion_posts": 2,
                "groups": 1,
                "proposals": 4,
                "reactions": 4,
                "text_documents": 1,
                "groups_reused": 1,
                "buttons_reused": 2,
            },
            importer.stats().dict(),
        )
        self.assertEqual(2, self.new_meeting.reaction_buttons.count())
        new_gilla_btn = self.new_meeting.reaction_buttons.get(title="Gilla")
        # New proposals with reactions intact!
        self.assertEqual(6, new_gilla_btn.reactions.count())
