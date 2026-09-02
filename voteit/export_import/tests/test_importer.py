import os
from io import StringIO

import yaml
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.test import override_settings
from django.test import TestCase

from voteit.discussion.models import DiscussionPost
from voteit.export_import.exceptions import SignatureVerificationFailed
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.notes import NoteIntent
from voteit.proposal.models import Proposal
from voteit.export_import.schemas import MeetingGroupData
from voteit.export_import.schemas import MeetingStructure
from voteit.export_import.tests import FIXTURES_DIR
from voteit.export_import.tests import read_fixture

User = get_user_model()


@override_settings(EXPORT_SECRET_KEY="abcdefghijk")
class ImporterTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.participant = cls.meeting.participants.get(username="participant")
        cls.moderator = cls.meeting.participants.get(username="moderator")
        cls.default_result = {
            "agenda_items": 3,
            "diff_proposals": 1,
            "discussion_posts": 2,
            "groups": 1,
            "proposals": 4,
            "text_documents": 1,
            "buttons": 2,
            "reactions": 0,
            "groups_reused": 0,
            "buttons_reused": 0,
            "notes": 0,
        }

    @property
    def _cut(self):
        from voteit.export_import.importer import Importer

        return Importer

    def test_collect_users(self):
        import_dict = read_fixture("combined_meeting_fixture.yaml")
        importer = self._cut(self.meeting)
        data = MeetingStructure(**import_dict)
        importer.data = data
        importer.collect_users()
        self.assertEqual({"participant": self.participant}, importer.user_map)

    def test_import_with_reactions_and_notes(self):
        importer = self._cut(self.meeting, include_reactions=True, include_notes=True)
        fn = os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml")
        importer.from_file(fn)
        importer.run()
        self.assertDictEqual(
            {"participant": self.participant, "moderator": self.moderator},
            importer.user_map,
        )
        self.assertDictEqual(
            {**self.default_result, "notes": 3, "reactions": 4},
            importer.stats().model_dump(),
        )
        self.assertEqual(
            {"Hot dogs", "Crisps", "Pickles"},
            set(self.meeting.agenda_items.values_list("title", flat=True)),
        )
        disc = DiscussionPost.objects.filter(tags__contains=["styrelse-1"]).get()
        self.assertEqual(self.participant, disc.author)
        meeting_group = self.meeting.groups.first()
        self.assertEqual("the-hellos", meeting_group.groupid)
        self.assertEqual(meeting_group, disc.meeting_group)
        self.assertEqual({self.participant}, set(meeting_group.members.all()))
        ai = self.meeting.agenda_items.get(title="Pickles")
        proposals = {x.prop_id: x for x in ai.proposals.select_subclasses().all()}

        discussion = ai.discussions.first()
        self.assertIn("styrelse-1", discussion.body)
        btn = self.meeting.reaction_buttons.filter(title="Gilla").first()
        self.assertEqual("Gilla", btn.title)
        self.assertEqual(3, btn.reactions.count())

        reactions_data = [
            dict(x)
            for x in btn.reactions.order_by("pk").values(
                "user", "agenda_item", "object_id", "content_type"
            )
        ]
        self.assertEqual(
            {
                "agenda_item": ai.pk,
                "content_type": ContentType.objects.get_for_model(Proposal).pk,
                "object_id": proposals["loeksas-2"].pk,
                "user": self.participant.pk,
            },
            reactions_data[0],
        )
        self.assertEqual(
            {
                "agenda_item": ai.pk,
                "content_type": ContentType.objects.get_for_model(Proposal).pk,
                "object_id": proposals["loeksas-2"].pk,
                "user": self.moderator.pk,
            },
            reactions_data[1],
        )
        self.assertEqual(
            {
                "agenda_item": ai.pk,
                "content_type": ContentType.objects.get_for_model(DiscussionPost).pk,
                "object_id": discussion.pk,
                "user": self.moderator.pk,
            },
            reactions_data[2],
        )

        btn2 = self.meeting.reaction_buttons.filter(
            title="Valberedningens förslag"
        ).first()
        self.assertEqual("Valberedningens förslag", btn2.title)
        self.assertEqual(1, btn2.reactions.count())

        reactions_data = [
            dict(x)
            for x in btn2.reactions.order_by("pk").values(
                "user", "agenda_item", "object_id", "content_type"
            )
        ]
        self.assertEqual(
            {
                "agenda_item": ai.pk,
                "content_type": ContentType.objects.get_for_model(Proposal).pk,
                "object_id": proposals["loeksas-1"].pk,
                "user": self.moderator.pk,
            },
            reactions_data[0],
        )
        # Notes
        notes_values = [
            dict(x)
            for x in self.meeting.notes.order_by("pk").values(
                "user",
                "body",
                "proposal_id",
                "body",
                "intent",
            )
        ]
        self.assertEqual(3, len(notes_values))
        self.assertDictEqual(
            {
                "user": self.moderator.id,
                "body": "I really like this proposal",
                "proposal_id": proposals["loeksas-1"].id,
                "intent": str(NoteIntent.APPROVE),
            },
            notes_values[0],
        )
        self.assertDictEqual(
            {
                "user": self.participant.id,
                "body": "I'm not sure what they're trying to say",
                "proposal_id": proposals["loeksas-1"].id,
                "intent": "",
            },
            notes_values[1],
        )
        self.assertDictEqual(
            {
                "user": self.participant.id,
                "body": "",
                "proposal_id": proposals["loeksas-2"].id,
                "intent": str(NoteIntent.DENY),
            },
            notes_values[2],
        )

    def test_import_already_existing_groups(self):
        self.meeting.groups.create(groupid="the-hellos", title="I'm a group")
        importer = self._cut(self.meeting, use_existing_groups=False)
        fn = os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml")
        importer.from_file(fn)
        with self.assertRaises(IntegrityError):
            importer.run()

    def test_import_use_already_existing_groups(self):
        meeting_group = self.meeting.groups.create(
            groupid="the-hellos", title="I'm a group"
        )
        importer = self._cut(self.meeting, use_existing_groups=True)
        fn = os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml")
        importer.from_file(fn)
        importer.run()
        self.assertEqual({self.participant}, set(meeting_group.members.all()))
        meeting_group.refresh_from_db()
        self.assertEqual("The Hellos", meeting_group.title)

    def test_import_groups_with_delegate_to(self):
        importer = self._cut(self.meeting, use_existing_groups=False)
        importer.data = MeetingStructure(
            groups=[
                MeetingGroupData(groupid="board", delegate_to="the-hellos"),
                MeetingGroupData(groupid="the-hellos"),
            ]
        )
        importer.collect_users()
        importer.populate()
        board: MeetingGroup = self.meeting.groups.get(groupid="board")
        the_hellos: MeetingGroup = self.meeting.groups.get(groupid="the-hellos")
        self.assertEqual(the_hellos, board.delegate_to)

    def test_import_with_missing_user_abort(self):
        self.participant.delete()
        fn = os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml")
        importer = self._cut(self.meeting)
        importer.from_file(fn)
        with self.assertRaises(User.DoesNotExist) as cm:
            importer.run()
        self.assertEqual(
            "Can't find users with the following data:\nparticipant",
            str(cm.exception),
        )

    def test_import_with_missing_user_blank(self):
        self.participant.delete()
        fn = os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml")
        importer = self._cut(self.meeting, missing_user="blank")
        importer.from_file(fn)
        importer.run()
        prop = Proposal.objects.get(prop_id="loeksas-1")
        self.assertIsNone(prop.author)

    def test_import_from_file(self):
        importer = self._cut(self.meeting)
        fn = os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml")
        importer.from_file(fn)
        importer.run()
        self.assertTrue(Proposal.objects.get(prop_id="loeksas-1"))

    def test_import_from_file_with_bad_signature(self):
        importer = self._cut(self.meeting)
        fn = os.path.join(FIXTURES_DIR, "bad_signature.yaml")
        with self.assertRaises(SignatureVerificationFailed):
            importer.from_file(fn)

    def test_import_add_participant(self):
        self.meeting.remove_roles(self.participant, ROLE_PARTICIPANT)
        importer = self._cut(self.meeting, add_participants=True)
        fn = os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml")
        importer.from_file(fn)
        importer.run()
        self.assertEqual({ROLE_PARTICIPANT}, self.meeting.get_roles(self.participant))

    def test_import_dont_add_participant(self):
        self.meeting.remove_roles(self.participant, ROLE_PARTICIPANT)
        importer = self._cut(self.meeting, add_participants=False)
        fn = os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml")
        importer.from_file(fn)
        importer.run()
        self.assertEqual(None, self.meeting.get_roles(self.participant))

    def test_clear_ai_states(self):
        importer = self._cut(self.meeting, clear_ai_states=True)
        fn = os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml")
        importer.from_file(fn)
        importer.run()
        self.assertEqual(
            "private", self.meeting.agenda_items.get(title="Pickles").state
        )

    def test_keep_ai_state(self):
        importer = self._cut(self.meeting, clear_ai_states=False)
        fn = os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml")
        importer.from_file(fn)
        importer.run()
        self.assertEqual(
            "upcoming", self.meeting.agenda_items.get(title="Pickles").state
        )

    def test_keep_proposal_states(self):
        fn = os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml")
        importer = self._cut(self.meeting, clear_proposal_states=False)
        importer.from_file(fn)
        importer.run()
        prop = Proposal.objects.get(prop_id="loeksas-1")
        self.assertEqual("approved", prop.state)

    def test_clear_proposal_states(self):
        fn = os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml")
        importer = self._cut(self.meeting, clear_proposal_states=True)
        importer.from_file(fn)
        importer.run()
        prop = Proposal.objects.get(prop_id="loeksas-1")
        self.assertEqual("published", prop.state)

    def test_len(self):
        importer = self._cut(self.meeting)
        self.assertEqual(0, len(importer))
        importer.from_file(os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml"))
        self.assertEqual(4, len(importer))

    def test_reactions_that_point_to_ignored_proposal(self):
        importer = self._cut(
            self.meeting, include_reactions=True, include_proposals=False
        )
        importer.from_file(os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml"))
        # Reaction shouldn't work since object doesn't exist
        self.assertEqual(
            {
                **self.default_result,
                "diff_proposals": 0,
                "reactions": 1,
                "proposals": 0,
            },
            importer.stats().model_dump(),
        )

    def test_stats(self):
        importer = self._cut(self.meeting)
        importer.from_file(os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml"))
        self.assertEqual(self.default_result, importer.stats().model_dump())
        importer = self._cut(self.meeting, include_notes=True, include_reactions=True)
        importer.from_file(os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml"))
        self.assertEqual(
            {**self.default_result, "notes": 3, "reactions": 4},
            importer.stats().model_dump(),
        )


@override_settings(EXPORT_SECRET_KEY="abcdefghijk")
class InjectionSanitizationTests(TestCase):
    """HTML, JS and SQL injection payloads in every schema field are sanitized on import."""

    fixtures = ["meeting_test_fixture"]

    # Every text field in the schema populated with at least one dangerous payload.
    # Payloads chosen to cover: reflected XSS, event-handler injection, javascript: URLs,
    # SVG/img vectors, and SQL injection (the last is harmless via ORM but worth noting).
    _MALICIOUS = {
        "meta": {
            "version": 1,
            "title": "<script>alert('meeting')</script>Evil Meeting",
            "description": "'; DROP TABLE meetings; --",
        },
        "agenda_items": [
            {
                "title": "<script>alert(1)</script>Injected Title",
                "body": "<b>bold kept</b><script>alert('body')</script><img src=x onerror=alert(1)>",
                "state": "upcoming",
                "proposals": [
                    {
                        "body": "<b>bold kept</b><script>alert('prop')</script><a href=\"javascript:alert(1)\">click</a>",
                    }
                ],
                "discussions": [
                    {
                        "body": "<em>em kept</em><script>alert('disc')</script><svg onload=alert(1)>",
                        "created": "2024-01-01T00:00:00+00:00",
                    }
                ],
                "text_documents": [
                    {
                        "title": "<script>alert('td')</script>Evil Doc",
                        "body": "'; DROP TABLE text_documents; --<script>alert('tdbody')</script>",
                        "base_tag": "evil-doc",
                        "created": "2024-01-01T00:00:00+00:00",
                    }
                ],
            }
        ],
        "groups": [
            {
                "title": "<script>alert('group')</script>Evil Group",
                "groupid": "evil-group",
                "body": "' OR '1'='1 <b>bold kept</b><script>alert('groupbody')</script>",
            }
        ],
    }

    # Patterns that must never survive into the DB.
    _DANGEROUS = ["<script>", "onerror", "onload", "javascript:", "alert("]

    @classmethod
    def setUpTestData(cls):
        from voteit.export_import.importer import Importer
        from voteit.export_import.utils import sign_payload

        cls.meeting = Meeting.objects.get(pk=1)
        payload = yaml.dump(cls._MALICIOUS, allow_unicode=True)
        signed = "sign: " + sign_payload(payload) + "\n" + payload
        importer = Importer(cls.meeting)
        importer.from_stream(StringIO(signed))
        importer.run()
        cls.importer = importer
        cls.ai = cls.meeting.agenda_items.get()
        cls.group = cls.meeting.groups.get()
        cls.proposal = cls.ai.proposals.get()
        cls.discussion = cls.ai.discussions.get()
        cls.text_doc = cls.ai.text_documents.get()

    # --- plain-text title fields: absolutely no HTML markup ---

    def test_agenda_item_title_has_no_html(self):
        self.assertNotIn("<", self.ai.title)
        self.assertIn("Injected Title", self.ai.title)

    def test_group_title_has_no_html(self):
        self.assertNotIn("<", self.group.title)
        self.assertIn("Evil Group", self.group.title)

    def test_text_document_title_has_no_html(self):
        self.assertNotIn("<", self.text_doc.title)
        self.assertIn("Evil Doc", self.text_doc.title)

    def test_text_document_body_has_no_html(self):
        # TextDocument.body is plaintext — strip_html removes everything
        self.assertNotIn("<", self.text_doc.body)
        self.assertNotIn(">", self.text_doc.body)

    # --- rich-text body fields: dangerous patterns gone, safe tags kept ---

    def test_agenda_item_body(self):
        for pattern in self._DANGEROUS:
            with self.subTest(pattern=pattern):
                self.assertNotIn(pattern, self.ai.body)
        self.assertIn("<b>", self.ai.body)

    def test_proposal_body(self):
        for pattern in self._DANGEROUS:
            with self.subTest(pattern=pattern):
                self.assertNotIn(pattern, self.proposal.body)
        self.assertIn("<b>", self.proposal.body)

    def test_discussion_body(self):
        for pattern in self._DANGEROUS:
            with self.subTest(pattern=pattern):
                self.assertNotIn(pattern, self.discussion.body)
        self.assertIn("<em>", self.discussion.body)

    def test_group_body(self):
        for pattern in self._DANGEROUS:
            with self.subTest(pattern=pattern):
                self.assertNotIn(pattern, self.group.body)
        self.assertIn("<b>", self.group.body)

    # --- meta fields are schema-only (not stored in DB) ---

    def test_meta_title_sanitized(self):
        self.assertNotIn("<script>", self.importer.data.meta.title)
        self.assertIn("Evil Meeting", self.importer.data.meta.title)

    def test_meta_description_sanitized(self):
        # SQL payload is plain text — harmless via ORM, but must not contain markup
        self.assertNotIn("<script>", self.importer.data.meta.description)
