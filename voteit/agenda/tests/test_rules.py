from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.agenda.models import AgendaItem
from voteit.core import PERM
from voteit.meeting.models import Meeting


class RulesTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        User = get_user_model()
        cls.outsider = User.objects.create(username="outsider")
        cls.participant = User.objects.get(username="participant")
        cls.moderator = User.objects.get(username="moderator")
        cls.ai = cls.meeting.agenda_items.create(state="upcoming")

    def setUp(self):
        super().setUp()
        self.meeting.refresh_from_db()
        self.ai.refresh_from_db()

    def p(self, perm):
        return AgendaItem.get_perm(perm)

    def _archive(self):
        self.meeting.state = "closed"
        self.meeting.archive()
        self.meeting.save()
        self.ai.refresh_from_db()

    def test_view_private(self):
        self.ai.state = "private"
        self.ai.save()
        VIEW = self.p(PERM.VIEW)
        self.assertFalse(self.outsider.has_perm(VIEW, self.ai))
        self.assertFalse(self.participant.has_perm(VIEW, self.ai))
        self.assertTrue(self.moderator.has_perm(VIEW, self.ai))

    def test_view_upcoming(self):
        VIEW = self.p(PERM.VIEW)
        self.assertFalse(self.outsider.has_perm(VIEW, self.ai))
        self.assertTrue(self.participant.has_perm(VIEW, self.ai))
        self.assertTrue(self.moderator.has_perm(VIEW, self.ai))

    def test_view_public_meeting_private_ai(self):
        self.ai.state = "private"
        self.ai.save()
        self.meeting.public = True
        self.meeting.save()
        VIEW = self.p(PERM.VIEW)
        self.assertFalse(self.outsider.has_perm(VIEW, self.ai))
        self.assertFalse(self.participant.has_perm(VIEW, self.ai))
        self.assertTrue(self.moderator.has_perm(VIEW, self.ai))

    def test_view_public_meeting(self):
        self.meeting.public = True
        self.meeting.save()
        VIEW = self.p(PERM.VIEW)
        self.assertTrue(self.outsider.has_perm(VIEW, self.ai))
        self.assertTrue(self.participant.has_perm(VIEW, self.ai))
        self.assertTrue(self.moderator.has_perm(VIEW, self.ai))

    def test_add(self):
        ADD = self.p(PERM.ADD)
        self.assertFalse(self.outsider.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))
        self.assertTrue(self.moderator.has_perm(ADD, self.meeting))

    def test_add_archived_meeting(self):
        self._archive()
        ADD = self.p(PERM.ADD)
        self.assertFalse(self.outsider.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))
        self.assertFalse(self.moderator.has_perm(ADD, self.meeting))

    def test_change(self):
        CHANGE = self.p(PERM.CHANGE)
        self.assertFalse(self.outsider.has_perm(CHANGE, self.ai))
        self.assertFalse(self.participant.has_perm(CHANGE, self.ai))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.ai))

    def test_change_archived_meeting(self):
        self._archive()
        CHANGE = self.p(PERM.CHANGE)
        self.assertFalse(self.outsider.has_perm(CHANGE, self.ai))
        self.assertFalse(self.participant.has_perm(CHANGE, self.ai))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.ai))

    def test_delete(self):
        DELETE = self.p(PERM.DELETE)
        self.assertFalse(self.outsider.has_perm(DELETE, self.ai))
        self.assertFalse(self.participant.has_perm(DELETE, self.ai))
        self.assertTrue(self.moderator.has_perm(DELETE, self.ai))

    def test_delete_archived_meeting(self):
        self._archive()
        DELETE = self.p(PERM.DELETE)
        self.assertFalse(self.outsider.has_perm(DELETE, self.ai))
        self.assertFalse(self.participant.has_perm(DELETE, self.ai))
        self.assertFalse(self.moderator.has_perm(DELETE, self.ai))
