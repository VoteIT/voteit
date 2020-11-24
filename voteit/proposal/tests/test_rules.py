from django.contrib.auth.models import User
from django.test import TestCase


class RulesTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_MODERATOR
        from voteit.meeting.roles import ROLE_PARTICIPANT
        from voteit.meeting.roles import ROLE_PROPOSER

        self.meeting = Meeting.objects.create()
        self.anon_user = User.objects.create(username="anon")
        self.participant = User.objects.create(username="participant")
        self.meeting.add_roles(self.participant, ROLE_PARTICIPANT)
        self.moderator = User.objects.create(username="moderator")
        self.meeting.add_roles(self.moderator, ROLE_MODERATOR)
        self.proposer = User.objects.create(username="proposer")
        self.proposer_author = User.objects.create(
            username="proposer_author"
        )
        self.meeting.add_roles(self.proposer, ROLE_PROPOSER)
        self.meeting.add_roles(self.proposer_author, ROLE_PROPOSER)
        self.ai = self.meeting.agenda_items.create()
        self.ai.upcoming()
        self.ai.save()
        self.proposal = self.ai.proposals.create(author=self.proposer_author)

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
        self.assertTrue(self.moderator.has_perm(CHANGE, self.proposal))
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
        self.assertTrue(self.moderator.has_perm(DELETE, self.proposal))
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
        self.assertTrue(self.moderator.has_perm(RETRACT, self.proposal))
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
