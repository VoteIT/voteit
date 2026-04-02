from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.core import PERM
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.room.models import Room


class RulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.meeting = Meeting.objects.create()
        cls.anon_user = User.objects.create(username="anon")
        cls.participant = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.moderator = User.objects.create(username="moderator")
        cls.moderator2 = User.objects.create(username="moderator2")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.meeting.add_roles(cls.moderator2, ROLE_MODERATOR)
        cls.room = cls.meeting.rooms.create()

    def setUp(self):
        self.meeting.refresh_from_db()

    def test_add(self):
        ADD = Room.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))
        self.assertTrue(self.moderator.has_perm(ADD, self.meeting))

    def test_add_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        ADD = Room.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))
        self.assertFalse(self.moderator.has_perm(ADD, self.meeting))

    def test_change(self):
        CHANGE = Room.get_perm(PERM.CHANGE)
        # Maybe we want to allow changes for authors later on...
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.room))
        self.assertFalse(self.participant.has_perm(CHANGE, self.room))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.room))

    def test_change_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        CHANGE = Room.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.room))
        self.assertFalse(self.participant.has_perm(CHANGE, self.room))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.room))

    def test_delete(self):
        DELETE = Room.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.room))
        self.assertFalse(self.participant.has_perm(DELETE, self.room))
        self.assertTrue(self.moderator.has_perm(DELETE, self.room))

    def test_handle_no_handler_set(self):
        HANDLE = Room.get_perm(PERM.HANDLE)
        self.assertFalse(self.anon_user.has_perm(HANDLE, self.room))
        self.assertFalse(self.participant.has_perm(HANDLE, self.room))
        self.assertFalse(self.moderator.has_perm(HANDLE, self.room))
        self.assertFalse(self.moderator2.has_perm(HANDLE, self.room))

    def test_handle(self):
        self.room.handler = self.moderator
        self.room.save()
        HANDLE = Room.get_perm(PERM.HANDLE)
        self.assertTrue(self.moderator.has_perm(HANDLE, self.room))
        self.assertFalse(self.moderator2.has_perm(HANDLE, self.room))
