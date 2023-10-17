from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT


class RulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.meeting = Meeting.objects.create()
        cls.anon_user = User.objects.create(username="anon")
        cls.participant = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.room = cls.meeting.rooms.create()

    def setUp(self):
        self.meeting.refresh_from_db()

    def p(self, perm):
        from voteit.room.permissions import RoomPermissions

        return getattr(RoomPermissions, perm)

    def test_view_upcoming(self):
        VIEW = self.p("VIEW")
        self.assertFalse(self.anon_user.has_perm(VIEW, self.room))
        self.assertTrue(self.participant.has_perm(VIEW, self.room))
        self.assertTrue(self.moderator.has_perm(VIEW, self.room))

    def test_add(self):
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))
        self.assertTrue(self.moderator.has_perm(ADD, self.meeting))

    def test_add_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))
        self.assertFalse(self.moderator.has_perm(ADD, self.meeting))

    def test_change(self):
        CHANGE = self.p("CHANGE")
        # Maybe we want to allow changes for authors later on...
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.room))
        self.assertFalse(self.participant.has_perm(CHANGE, self.room))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.room))

    def test_change_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.room))
        self.assertFalse(self.participant.has_perm(CHANGE, self.room))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.room))

    def test_delete(self):
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(DELETE, self.room))
        self.assertFalse(self.participant.has_perm(DELETE, self.room))
        self.assertTrue(self.moderator.has_perm(DELETE, self.room))
