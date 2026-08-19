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
        cls.default_stats = {
            "agenda_items": 3,
            "buttons": 2,
            "diff_proposals": 1,
            "discussion_posts": 2,
            "groups": 1,
            "proposals": 4,
            "reactions": 0,
            "text_documents": 1,
            "groups_reused": 0,
            "buttons_reused": 0,
            "notes": 0,
        }

    def test_direct_clone(self):
        importer = direct_clone(
            source=self.meeting,
            target=self.new_meeting,
            dry_run=False,
            include_reactions=True,
        )
        self.assertEqual(
            {**self.default_stats, "reactions": 4}, importer.stats().dict()
        )
        self.assertSetEqual(
            self.meeting.agenda_items.values_list("title", flat=True),
            self.new_meeting.agenda_items.values_list("title", flat=True),
        )

    def test_direct_clone_no_commit(self):
        importer = direct_clone(
            source=self.meeting,
            target=self.new_meeting,
            dry_run=True,
            include_reactions=True,
        )
        self.assertEqual(
            {**self.default_stats, "reactions": 4},
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
            dry_run=True,
            include_reactions=True,
            include_discussions=False,
        )
        self.assertEqual(
            {**self.default_stats, "discussion_posts": 0, "reactions": 3},
            importer.stats().dict(),
        )

    def test_direct_clone_notes(self):
        importer = direct_clone(
            source=self.meeting,
            target=self.new_meeting,
            dry_run=True,
            include_notes=True,
        )
        self.assertEqual(
            {
                **self.default_stats,
                "notes": 3,
            },
            importer.stats().dict(),
        )

    def test_direct_clone_group_with_delegate_to(self):
        the_hellos = self.meeting.groups.get(groupid="the-hellos")
        self.meeting.groups.create(title="Delegating group", delegate_to=the_hellos)
        importer = direct_clone(
            source=self.meeting,
            target=self.new_meeting,
            dry_run=False,
        )
        self.assertEqual({**self.default_stats, "groups": 2}, importer.stats().dict())
        cloned_the_hellos = self.new_meeting.groups.get(groupid="the-hellos")
        cloned_delegating = self.new_meeting.groups.get(groupid="delegating-group")
        self.assertEqual(cloned_the_hellos, cloned_delegating.delegate_to)

    def test_direct_clone_bad_options(self):
        with self.assertRaises(ValidationError) as cm:
            direct_clone(
                source=self.meeting,
                target=self.new_meeting,
                include_reactions=True,
                include_buttons=False,
            )
        # pydantic v2 errors() also carries ctx/url and prefixes the message
        # with "Value error, ", so assert on the parts that carry meaning.
        self.assertEqual(
            [
                {
                    "loc": ("include_reactions",),
                    "msg": "Buttons are needed to set reactions - change 'include_buttons'",
                    "type": "value_error",
                }
            ],
            [
                {
                    "loc": e["loc"],
                    "msg": e["msg"].removeprefix("Value error, "),
                    "type": e["type"],
                }
                for e in cm.exception.errors()
            ],
        )

    def test_clone_flags(self):
        self.btn.flag = True
        self.btn.save()
        importer = direct_clone(
            source=self.meeting,
            target=self.new_meeting,
            dry_run=False,
            include_reactions=True,
        )
        self.assertEqual(
            {**self.default_stats, "reactions": 4},
            importer.stats().dict(),
        )
        # And once again
        importer = direct_clone(
            source=self.meeting,
            target=self.new_meeting,
            dry_run=False,
            include_reactions=True,
        )
        self.assertEqual(
            {
                **self.default_stats,
                "reactions": 4,
                "groups_reused": 1,
                "buttons_reused": 2,
            },
            importer.stats().dict(),
        )
        self.assertEqual(2, self.new_meeting.reaction_buttons.count())
        new_gilla_btn = self.new_meeting.reaction_buttons.get(title="Gilla")
        # New proposals with reactions intact!
        self.assertEqual(6, new_gilla_btn.reactions.count())


class CloneMaxLengthTitleTests(TestCase):
    """Clone must handle group/agenda-item titles of exactly 100 characters.

    Titles containing special HTML characters like '&' were broken because
    strip_html (nh3.clean) escapes them to entities (&amp;), making a 100-char
    title exceed the schema's max_length=100 constraint.
    """

    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org = Meeting.objects.get(pk=1).organisation
        cls.source = cls.org.meetings.create()
        # 97 plain chars + ' & ' = 100 chars, but '&' expands to '&amp;' in nh3
        cls.amp_title = "Meeting group & subcommittee on budget" + "X" * 62
        cls.plain_title = "A" * 100
        cls.source.groups.create(title=cls.amp_title, groupid="amp-group")
        cls.source.groups.create(title=cls.plain_title, groupid="a" * 100)
        cls.source.agenda_items.create(title=cls.amp_title)
        cls.source.agenda_items.create(title=cls.plain_title)

    def setUp(self):
        self.target = self.org.meetings.create()

    def test_clone_with_special_char_titles_at_max_length(self):
        importer = direct_clone(
            source=self.source,
            target=self.target,
            dry_run=False,
        )
        self.assertEqual(2, self.target.groups.count())
        self.assertEqual(2, self.target.agenda_items.count())
        stats = importer.stats().dict()
        self.assertEqual(2, stats["groups"])
        self.assertEqual(2, stats["agenda_items"])
        titles = set(self.target.agenda_items.values_list("title", flat=True))
        self.assertIn(self.amp_title, titles)
        self.assertIn(self.plain_title, titles)
