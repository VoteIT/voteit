import os

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.test import override_settings
from django.test import TestCase

from voteit.discussion.models import DiscussionPost
from voteit.export_import.exceptions import SignatureVerificationFailed
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.proposal.models import DiffProposal
from voteit.proposal.models import Proposal
from voteit.proposal.workflows import ProposalWf
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

    def test_import(self):
        importer = self._cut(self.meeting, include_reactions=True)
        fn = os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml")
        importer.from_file(fn)
        importer.run()
        self.assertEqual(
            {"participant": self.participant, "moderator": self.moderator},
            importer.user_map,
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

    def test_import_already_existing_groups(self):
        meeting_group = self.meeting.groups.create(
            groupid="the-hellos", title="I'm a group"
        )
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
        import_dict = read_fixture("combined_meeting_fixture.yaml")
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
        self.assertEqual(ProposalWf.APPROVED, prop.state)

    def test_clear_proposal_states(self):
        fn = os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml")
        importer = self._cut(self.meeting, clear_proposal_states=True)
        importer.from_file(fn)
        importer.run()
        prop = Proposal.objects.get(prop_id="loeksas-1")
        self.assertEqual(ProposalWf.PUBLISHED, prop.state)

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
                "agenda_items": 3,
                "diff_proposals": 0,
                "discussion_posts": 2,
                "groups": 1,
                "proposals": 0,
                "text_documents": 1,
                "buttons": 2,
                "reactions": 1,
                "groups_reused": 0,
                "buttons_reused": 0,
            },
            importer.stats().dict(),
        )

    def test_stats(self):
        importer = self._cut(self.meeting, include_reactions=1)
        importer.from_file(os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml"))
        self.assertEqual(
            {
                "agenda_items": 3,
                "diff_proposals": 1,
                "discussion_posts": 2,
                "groups": 1,
                "proposals": 4,
                "text_documents": 1,
                "buttons": 2,
                "reactions": 4,
                "groups_reused": 0,
                "buttons_reused": 0,
            },
            importer.stats().dict(),
        )
