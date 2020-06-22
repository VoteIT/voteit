from django.contrib.auth.models import User
from django.test import TestCase


class RulesTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        self.meeting = Meeting.objects.create()
        self.anon_user = User.objects.create(username="anon")
        self.participant = self.meeting.participants.create(username="participant")
        self.moderator = self.meeting.moderators.create(username="moderator")
        self.ai = self.meeting.agenda_items.create()
        self.ai.upcoming()
        self.ai.save()

    def p(self, perm):
        from voteit.agenda.permissions import AgendaPermissions
        return getattr(AgendaPermissions, perm)

    def _archive(self):
        self.meeting.ongoing()
        self.meeting.close()
        self.meeting.archive()
        self.meeting.save()

    def test_view_private(self):
        self.ai.unpublish()
        self.ai.save()
        VIEW = self.p("VIEW")
        self.assertFalse(self.anon_user.has_perm(VIEW, self.ai))
        self.assertFalse(self.participant.has_perm(VIEW, self.ai))
        self.assertTrue(self.moderator.has_perm(VIEW, self.ai))

    def test_view_upcoming(self):
        VIEW = self.p("VIEW")
        self.assertFalse(self.anon_user.has_perm(VIEW, self.ai))
        self.assertTrue(self.participant.has_perm(VIEW, self.ai))
        self.assertTrue(self.moderator.has_perm(VIEW, self.ai))

    def test_view_public_meeting_private_ai(self):
        self.ai.unpublish()
        self.ai.save()
        self.meeting.public = True
        self.meeting.save()
        VIEW = self.p("VIEW")
        self.assertFalse(self.anon_user.has_perm(VIEW, self.ai))
        self.assertFalse(self.participant.has_perm(VIEW, self.ai))
        self.assertTrue(self.moderator.has_perm(VIEW, self.ai))

    def test_view_public_meeting(self):
        self.meeting.public = True
        self.meeting.save()
        VIEW = self.p("VIEW")
        self.assertTrue(self.anon_user.has_perm(VIEW, self.ai))
        self.assertTrue(self.participant.has_perm(VIEW, self.ai))
        self.assertTrue(self.moderator.has_perm(VIEW, self.ai))

    def test_add(self):
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))
        self.assertTrue(self.moderator.has_perm(ADD, self.meeting))

    def test_add_archived_meeting(self):
        self._archive()
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))
        self.assertFalse(self.moderator.has_perm(ADD, self.meeting))

    def test_change(self):
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.ai))
        self.assertFalse(self.participant.has_perm(CHANGE, self.ai))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.ai))

    def test_change_archived_meeting(self):
        self._archive()
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.ai))
        self.assertFalse(self.participant.has_perm(CHANGE, self.ai))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.ai))

    def test_delete(self):
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(DELETE, self.ai))
        self.assertFalse(self.participant.has_perm(DELETE, self.ai))
        self.assertTrue(self.moderator.has_perm(DELETE, self.ai))

    def test_delete_archived_meeting(self):
        self._archive()
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(DELETE, self.ai))
        self.assertFalse(self.participant.has_perm(DELETE, self.ai))
        self.assertFalse(self.moderator.has_perm(DELETE, self.ai))
