from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.core import PERM
from voteit.proposal import PERM_RETRACT
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument


class RulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_MODERATOR
        from voteit.meeting.roles import ROLE_PARTICIPANT
        from voteit.meeting.roles import ROLE_PROPOSER

        User = get_user_model()
        cls.meeting = Meeting.objects.create(er_policy_name="auto_before_poll")
        cls.anon_user = User.objects.create(username="anon")
        cls.participant = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.group_proposer = User.objects.create(username="group_proposer")
        cls.meeting.add_roles(cls.group_proposer, ROLE_PARTICIPANT, ROLE_PROPOSER)
        cls.group_participant = User.objects.create(username="group_participant")
        cls.meeting.add_roles(cls.group_participant, ROLE_PARTICIPANT)
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.proposer = User.objects.create(username="proposer")
        cls.proposer_author = User.objects.create(username="proposer_author")
        cls.meeting.add_roles(cls.proposer, ROLE_PROPOSER)
        cls.meeting.add_roles(cls.proposer_author, ROLE_PROPOSER)
        cls.ai = cls.meeting.agenda_items.create()
        cls.ai.state = "upcoming"
        cls.ai.save()
        cls.group = cls.meeting.groups.create()
        cls.group.members.add(cls.group_proposer, cls.group_participant)
        cls.proposal = cls.ai.proposals.create(
            author=cls.proposer_author, meeting_group=cls.group
        )

    def setUp(self):
        self.ai.refresh_from_db()
        self.meeting.refresh_from_db()

    def _archive(self):
        self.meeting.archive()
        self.meeting.save()
        self.ai.refresh_from_db()

    def test_add(self):
        ADD = Proposal.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.ai))
        self.assertFalse(self.participant.has_perm(ADD, self.ai))
        self.assertTrue(self.moderator.has_perm(ADD, self.ai))
        self.assertTrue(self.proposer.has_perm(ADD, self.ai))
        self.assertTrue(self.group_proposer.has_perm(ADD, self.ai))
        self.assertFalse(self.group_participant.has_perm(ADD, self.ai))

    def test_add_with_block(self):
        self.ai.block_proposals = True
        self.ai.save()
        ADD = Proposal.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.ai))
        self.assertFalse(self.participant.has_perm(ADD, self.ai))
        self.assertTrue(self.moderator.has_perm(ADD, self.ai))
        self.assertFalse(self.proposer.has_perm(ADD, self.ai))
        self.assertFalse(self.group_proposer.has_perm(ADD, self.ai))
        self.assertFalse(self.group_participant.has_perm(ADD, self.ai))

    def test_add_closed_ai_ongoing_meeting(self):
        self.ai.state = "closed"
        self.ai.save()
        ADD = Proposal.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.ai))
        self.assertFalse(self.participant.has_perm(ADD, self.ai))
        self.assertFalse(self.moderator.has_perm(ADD, self.ai))
        self.assertFalse(self.proposer.has_perm(ADD, self.ai))
        self.assertFalse(self.group_proposer.has_perm(ADD, self.ai))
        self.assertFalse(self.group_participant.has_perm(ADD, self.ai))

    def test_add_closed_meeting_closed_ai(self):
        # Note: Meetings shouldn't be able to close without closing the AIs
        self.meeting.state = "closed"
        self.ai.state = "closed"
        self.ai.save()
        ADD = Proposal.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.ai))
        self.assertFalse(self.participant.has_perm(ADD, self.ai))
        self.assertFalse(self.moderator.has_perm(ADD, self.ai))
        self.assertFalse(self.proposer.has_perm(ADD, self.ai))
        self.assertFalse(self.group_proposer.has_perm(ADD, self.ai))
        self.assertFalse(self.group_participant.has_perm(ADD, self.ai))

    def test_add_archived_meeting(self):
        self._archive()
        ADD = Proposal.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.ai))
        self.assertFalse(self.participant.has_perm(ADD, self.ai))
        self.assertFalse(self.moderator.has_perm(ADD, self.ai))
        self.assertFalse(self.proposer.has_perm(ADD, self.ai))
        self.assertFalse(self.group_proposer.has_perm(ADD, self.ai))
        self.assertFalse(self.group_participant.has_perm(ADD, self.ai))

    def test_change(self):
        CHANGE = Proposal.get_perm(PERM.CHANGE)
        # Maybe we want to allow changes for authors later on...
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.participant.has_perm(CHANGE, self.proposal))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.proposer.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.group_proposer.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.group_participant.has_perm(CHANGE, self.proposal))

    def test_change_closed_ai_ongoing_meeting(self):
        self.meeting.state = "ongoing"
        self.meeting.save()
        self.ai.state = "closed"
        self.ai.save()
        self.ai.save()
        CHANGE = Proposal.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.participant.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.proposer.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.group_proposer.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.group_participant.has_perm(CHANGE, self.proposal))

    def test_change_closed_meeting_closed_ai(self):
        self.meeting.state = "closed"
        self.meeting.save()
        self.ai.state = "closed"
        self.ai.save()
        self.ai.save()
        CHANGE = Proposal.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.participant.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.proposer.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.group_proposer.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.group_participant.has_perm(CHANGE, self.proposal))

    def test_change_archived_meeting(self):
        self._archive()
        CHANGE = Proposal.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.participant.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.proposer.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.group_proposer.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.group_participant.has_perm(CHANGE, self.proposal))

    def test_delete(self):
        DELETE = Proposal.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.proposal))
        self.assertFalse(self.participant.has_perm(DELETE, self.proposal))
        self.assertTrue(self.moderator.has_perm(DELETE, self.proposal))
        self.assertFalse(self.proposer.has_perm(DELETE, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(DELETE, self.proposal))
        self.assertFalse(self.group_proposer.has_perm(DELETE, self.proposal))
        self.assertFalse(self.group_participant.has_perm(DELETE, self.proposal))

    def test_delete_closed_ai_ongoing_meeting(self):
        self.meeting.state = "ongoing"
        self.meeting.save()
        self.ai.state = "closed"
        self.ai.save()
        self.ai.save()
        DELETE = Proposal.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.proposal))
        self.assertFalse(self.participant.has_perm(DELETE, self.proposal))
        self.assertFalse(self.moderator.has_perm(DELETE, self.proposal))
        self.assertFalse(self.proposer.has_perm(DELETE, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(DELETE, self.proposal))
        self.assertFalse(self.group_proposer.has_perm(DELETE, self.proposal))
        self.assertFalse(self.group_participant.has_perm(DELETE, self.proposal))

    def test_delete_closed_meeting_closed_ai(self):
        self.meeting.state = "closed"
        self.meeting.save()
        self.ai.state = "closed"
        self.ai.save()
        self.ai.save()
        DELETE = Proposal.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.proposal))
        self.assertFalse(self.participant.has_perm(DELETE, self.proposal))
        self.assertFalse(self.moderator.has_perm(DELETE, self.proposal))
        self.assertFalse(self.proposer.has_perm(DELETE, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(DELETE, self.proposal))
        self.assertFalse(self.group_proposer.has_perm(DELETE, self.proposal))
        self.assertFalse(self.group_participant.has_perm(DELETE, self.proposal))

    def test_delete_archived_meeting(self):
        self._archive()
        DELETE = Proposal.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.proposal))
        self.assertFalse(self.participant.has_perm(DELETE, self.proposal))
        self.assertFalse(self.moderator.has_perm(DELETE, self.proposal))
        self.assertFalse(self.proposer.has_perm(DELETE, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(DELETE, self.proposal))
        self.assertFalse(self.group_proposer.has_perm(DELETE, self.proposal))
        self.assertFalse(self.group_participant.has_perm(DELETE, self.proposal))

    def test_retract(self):
        RETRACT = Proposal.get_perm(PERM_RETRACT)
        self.assertFalse(self.anon_user.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.participant.has_perm(RETRACT, self.proposal))
        self.assertTrue(self.moderator.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer.has_perm(RETRACT, self.proposal))
        self.assertTrue(self.proposer_author.has_perm(RETRACT, self.proposal))
        self.assertTrue(self.group_proposer.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.group_participant.has_perm(RETRACT, self.proposal))

    def test_retract_archived_meeting(self):
        self._archive()
        RETRACT = Proposal.get_perm(PERM_RETRACT)
        self.assertFalse(self.anon_user.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.participant.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.moderator.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.group_proposer.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.group_participant.has_perm(RETRACT, self.proposal))

    def test_retract_private_ai(self):
        self.ai.state = "private"
        self.ai.save()
        self.ai.save()
        RETRACT = Proposal.get_perm(PERM_RETRACT)
        self.assertFalse(self.anon_user.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.participant.has_perm(RETRACT, self.proposal))
        self.assertTrue(self.moderator.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.group_proposer.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.group_participant.has_perm(RETRACT, self.proposal))

    def test_retract_closed_ai_ongoing_meeting(self):
        self.ai.state = "closed"
        self.ai.save()
        self.ai.save()
        RETRACT = Proposal.get_perm(PERM_RETRACT)
        self.assertFalse(self.anon_user.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.participant.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.moderator.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.group_proposer.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.group_participant.has_perm(RETRACT, self.proposal))

    def test_retract_closed_meeting_closed_ai(self):
        self.ai.state = "closed"
        self.ai.save()
        self.meeting.state = "closed"
        RETRACT = Proposal.get_perm(PERM_RETRACT)
        self.assertFalse(self.anon_user.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.participant.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.moderator.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.group_proposer.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.group_participant.has_perm(RETRACT, self.proposal))


TEXT = """
I'm sorry, but I don't want to be an emperor

That's not my business

I don't want to rule or conquer anyone
"""


class TextDocumentPermissionsTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.agenda.models import AgendaItem
        from voteit.proposal.models import TextDocument
        from voteit.proposal.models import TextParagraph

        User = get_user_model()

        cls.meeting = Meeting.objects.get(pk=1)
        cls.meeting.state = "ongoing"
        cls.meeting.save()
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(state="ongoing")
        cls.participant = cls.meeting.participants.get(username="participant")
        cls.moderator = cls.meeting.participants.get(username="moderator")
        cls.outsider = User.objects.create(username="outsider")
        cls.text_doc: TextDocument = cls.ai.text_documents.create(body=TEXT)
        cls.para: TextParagraph = cls.text_doc.text_paragraphs.first()  # Any will do

    def setUp(self):
        self.ai.refresh_from_db()

    def _mk_prop(self):
        self.para.proposals.create()

    def test_add_ongoing_ai(self):
        ADD = TextDocument.get_perm(PERM.ADD)
        self.assertFalse(self.participant.has_perm(ADD, self.ai))
        self.assertTrue(self.moderator.has_perm(ADD, self.ai))
        self.assertFalse(self.outsider.has_perm(ADD, self.ai))

    def test_add_closed_ai(self):
        self.ai.state = "closed"
        self.ai.save()
        ADD = TextDocument.get_perm(PERM.ADD)
        self.assertFalse(self.participant.has_perm(ADD, self.ai))
        self.assertFalse(self.moderator.has_perm(ADD, self.ai))
        self.assertFalse(self.outsider.has_perm(ADD, self.ai))

    def test_change_ongoing_ai(self):
        CHANGE = TextDocument.get_perm(PERM.CHANGE)
        self.assertFalse(self.participant.has_perm(CHANGE, self.text_doc))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.text_doc))
        self.assertFalse(self.outsider.has_perm(CHANGE, self.text_doc))

    def test_change_closed_ai(self):
        self.ai.state = "closed"
        self.ai.save()
        CHANGE = TextDocument.get_perm(PERM.CHANGE)
        self.assertFalse(self.participant.has_perm(CHANGE, self.text_doc))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.text_doc))
        self.assertFalse(self.outsider.has_perm(CHANGE, self.text_doc))

    def test_change_ongoing_ai_with_proposals(self):
        self._mk_prop()
        CHANGE = TextDocument.get_perm(PERM.CHANGE)
        self.assertFalse(self.participant.has_perm(CHANGE, self.text_doc))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.text_doc))
        self.assertFalse(self.outsider.has_perm(CHANGE, self.text_doc))

    def test_delete_ongoing_ai(self):
        DELETE = TextDocument.get_perm(PERM.DELETE)
        self.assertFalse(self.participant.has_perm(DELETE, self.text_doc))
        self.assertTrue(self.moderator.has_perm(DELETE, self.text_doc))
        self.assertFalse(self.outsider.has_perm(DELETE, self.text_doc))

    def test_delete_closed_ai(self):
        self.ai.state = "closed"
        self.ai.save()
        DELETE = TextDocument.get_perm(PERM.DELETE)
        self.assertFalse(self.participant.has_perm(DELETE, self.text_doc))
        self.assertFalse(self.moderator.has_perm(DELETE, self.text_doc))
        self.assertFalse(self.outsider.has_perm(DELETE, self.text_doc))

    def test_delete_ongoing_ai_proposals(self):
        self._mk_prop()
        DELETE = TextDocument.get_perm(PERM.DELETE)
        self.assertFalse(self.participant.has_perm(DELETE, self.text_doc))
        self.assertFalse(self.moderator.has_perm(DELETE, self.text_doc))
        self.assertFalse(self.outsider.has_perm(DELETE, self.text_doc))
