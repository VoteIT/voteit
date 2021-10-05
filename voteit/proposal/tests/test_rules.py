from django.contrib.auth import get_user_model
from django.test import TestCase


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
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.proposer = User.objects.create(username="proposer")
        cls.proposer_author = User.objects.create(username="proposer_author")
        cls.meeting.add_roles(cls.proposer, ROLE_PROPOSER)
        cls.meeting.add_roles(cls.proposer_author, ROLE_PROPOSER)
        cls.ai = cls.meeting.agenda_items.create()
        cls.ai.upcoming()
        cls.ai.save()
        cls.proposal = cls.ai.proposals.create(author=cls.proposer_author)

    def setUp(self):
        self.ai.refresh_from_db()
        self.meeting.refresh_from_db()

    def p(self, perm):
        from voteit.proposal.permissions import ProposalPermissions

        return getattr(ProposalPermissions, perm)

    def _archive(self):
        self.meeting.archive()
        self.meeting.save()
        self.ai.refresh_from_db()

    def test_view_private(self):
        self.ai.unpublish()
        self.ai.save()
        VIEW = self.p("VIEW")
        self.assertFalse(self.anon_user.has_perm(VIEW, self.proposal))
        self.assertFalse(self.participant.has_perm(VIEW, self.proposal))
        self.assertTrue(self.moderator.has_perm(VIEW, self.proposal))
        self.assertFalse(self.proposer.has_perm(VIEW, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(VIEW, self.proposal))

    def test_view_upcoming(self):
        VIEW = self.p("VIEW")
        self.assertFalse(self.anon_user.has_perm(VIEW, self.proposal))
        self.assertTrue(self.participant.has_perm(VIEW, self.proposal))
        self.assertTrue(self.moderator.has_perm(VIEW, self.proposal))
        self.assertTrue(self.proposer.has_perm(VIEW, self.proposal))
        self.assertTrue(self.proposer_author.has_perm(VIEW, self.proposal))

    def test_view_public_meeting_private_ai(self):
        self.ai.unpublish()
        self.ai.save()
        self.meeting.public = True
        self.meeting.save()
        VIEW = self.p("VIEW")
        self.assertFalse(self.anon_user.has_perm(VIEW, self.proposal))
        self.assertFalse(self.participant.has_perm(VIEW, self.proposal))
        self.assertTrue(self.moderator.has_perm(VIEW, self.proposal))
        self.assertFalse(self.proposer.has_perm(VIEW, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(VIEW, self.proposal))

    def test_view_public_meeting(self):
        self.meeting.public = True
        self.meeting.save()
        VIEW = self.p("VIEW")
        self.assertTrue(self.anon_user.has_perm(VIEW, self.proposal))
        self.assertTrue(self.participant.has_perm(VIEW, self.proposal))
        self.assertTrue(self.moderator.has_perm(VIEW, self.proposal))
        self.assertTrue(self.proposer.has_perm(VIEW, self.proposal))
        self.assertTrue(self.proposer_author.has_perm(VIEW, self.proposal))

    def test_add(self):
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, self.ai))
        self.assertFalse(self.participant.has_perm(ADD, self.ai))
        self.assertTrue(self.moderator.has_perm(ADD, self.ai))
        self.assertTrue(self.proposer.has_perm(ADD, self.ai))

    def test_add_with_block(self):
        self.ai.block_proposals = True
        self.ai.save()
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, self.ai))
        self.assertFalse(self.participant.has_perm(ADD, self.ai))
        self.assertTrue(self.moderator.has_perm(ADD, self.ai))
        self.assertFalse(self.proposer.has_perm(ADD, self.ai))

    def test_add_closed_ai_ongoing_meeting(self):
        self.ai.close()
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, self.ai))
        self.assertFalse(self.participant.has_perm(ADD, self.ai))
        self.assertFalse(self.moderator.has_perm(ADD, self.ai))
        self.assertFalse(self.proposer.has_perm(ADD, self.ai))

    def test_add_closed_meeting_closed_ai(self):
        # Note: Meetings shouldn't be able to close without closing the AIs
        self.meeting.ongoing()
        self.meeting.close()
        self.ai.close()
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, self.ai))
        self.assertFalse(self.participant.has_perm(ADD, self.ai))
        self.assertFalse(self.moderator.has_perm(ADD, self.ai))
        self.assertFalse(self.proposer.has_perm(ADD, self.ai))

    def test_add_archived_meeting(self):
        self._archive()
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, self.ai))
        self.assertFalse(self.participant.has_perm(ADD, self.ai))
        self.assertFalse(self.moderator.has_perm(ADD, self.ai))
        self.assertFalse(self.proposer.has_perm(ADD, self.ai))

    def test_change(self):
        CHANGE = self.p("CHANGE")
        # Maybe we want to allow changes for authors later on...
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.participant.has_perm(CHANGE, self.proposal))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.proposer.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(CHANGE, self.proposal))

    def test_change_closed_ai_ongoing_meeting(self):
        self.meeting.ongoing()
        self.meeting.save()
        self.ai.close()
        self.ai.save()
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.participant.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.proposer.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(CHANGE, self.proposal))

    def test_change_closed_meeting_closed_ai(self):
        self.meeting.ongoing()
        self.meeting.close()
        self.meeting.save()
        self.ai.close()
        self.ai.save()
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.participant.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.proposer.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(CHANGE, self.proposal))

    def test_change_archived_meeting(self):
        self._archive()
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.participant.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.proposer.has_perm(CHANGE, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(CHANGE, self.proposal))

    def test_delete(self):
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(DELETE, self.proposal))
        self.assertFalse(self.participant.has_perm(DELETE, self.proposal))
        self.assertTrue(self.moderator.has_perm(DELETE, self.proposal))
        self.assertFalse(self.proposer.has_perm(DELETE, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(DELETE, self.proposal))

    def test_delete_closed_ai_ongoing_meeting(self):
        self.meeting.ongoing()
        self.meeting.save()
        self.ai.close()
        self.ai.save()
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(DELETE, self.proposal))
        self.assertFalse(self.participant.has_perm(DELETE, self.proposal))
        self.assertFalse(self.moderator.has_perm(DELETE, self.proposal))
        self.assertFalse(self.proposer.has_perm(DELETE, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(DELETE, self.proposal))

    def test_delete_closed_meeting_closed_ai(self):
        self.meeting.ongoing()
        self.meeting.close()
        self.meeting.save()
        self.ai.close()
        self.ai.save()
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(DELETE, self.proposal))
        self.assertFalse(self.participant.has_perm(DELETE, self.proposal))
        self.assertFalse(self.moderator.has_perm(DELETE, self.proposal))
        self.assertFalse(self.proposer.has_perm(DELETE, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(DELETE, self.proposal))

    def test_delete_archived_meeting(self):
        self._archive()
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(DELETE, self.proposal))
        self.assertFalse(self.participant.has_perm(DELETE, self.proposal))
        self.assertFalse(self.moderator.has_perm(DELETE, self.proposal))
        self.assertFalse(self.proposer.has_perm(DELETE, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(DELETE, self.proposal))

    def test_retract(self):
        RETRACT = self.p("RETRACT")
        self.assertFalse(self.anon_user.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.participant.has_perm(RETRACT, self.proposal))
        self.assertTrue(self.moderator.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer.has_perm(RETRACT, self.proposal))
        self.assertTrue(self.proposer_author.has_perm(RETRACT, self.proposal))

    def test_retract_archived_meeting(self):
        self._archive()
        RETRACT = self.p("RETRACT")
        self.assertFalse(self.anon_user.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.participant.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.moderator.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(RETRACT, self.proposal))

    def test_retract_private_ai(self):
        self.ai.unpublish()
        self.ai.save()
        RETRACT = self.p("RETRACT")
        self.assertFalse(self.anon_user.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.participant.has_perm(RETRACT, self.proposal))
        self.assertTrue(self.moderator.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(RETRACT, self.proposal))

    def test_retract_closed_ai_ongoing_meeting(self):
        self.ai.close()
        self.ai.save()
        RETRACT = self.p("RETRACT")
        self.assertFalse(self.anon_user.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.participant.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.moderator.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(RETRACT, self.proposal))

    def test_retract_closed_meeting_closed_ai(self):
        self.ai.close()
        self.meeting.ongoing()
        self.meeting.close()
        RETRACT = self.p("RETRACT")
        self.assertFalse(self.anon_user.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.participant.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.moderator.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer.has_perm(RETRACT, self.proposal))
        self.assertFalse(self.proposer_author.has_perm(RETRACT, self.proposal))
