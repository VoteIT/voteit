from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.roles import ROLE_LIST_MODERATOR
from voteit.speaker.roles import ROLE_SPEAKER

User = get_user_model()


class SpeakerListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.room = cls.meeting.rooms.create()
        cls.system: SpeakerListSystem = cls.meeting.speaker_systems.create(
            method_name="simple",
            state="active",
            meeting_roles_to_speaker=[ROLE_PROPOSER],
            room=cls.room,
        )
        cls.user_meeting_moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.user_meeting_moderator, ROLE_MODERATOR)
        cls.user_list_moderator = User.objects.create(username="list_moderator")
        cls.system.add_roles(cls.user_list_moderator, ROLE_LIST_MODERATOR)
        cls.user_speaker = User.objects.create(username="in")
        cls.user_proposer = User.objects.create(username="proposer")
        cls.system.add_roles(cls.user_speaker, ROLE_SPEAKER)
        cls.meeting.add_roles(cls.user_proposer, ROLE_PROPOSER)
        cls.user_any = User.objects.create(username="jane")
        cls.list: SpeakerList = cls.system.speaker_lists.create()
        cls.system.active_list = cls.list
        cls.system.save()

    def setUp(self):
        self.system.refresh_from_db()
        self.meeting.refresh_from_db()
        self.list.refresh_from_db()

    def p(self, name):
        from voteit.speaker.permissions import SpeakerListPermissions

        return getattr(SpeakerListPermissions, name)

    def test_add_speaker_list(self):
        ADD = self.p("ADD")
        self.assertTrue(self.user_meeting_moderator.has_perm(ADD, self.system))
        self.assertTrue(self.user_list_moderator.has_perm(ADD, self.system))
        self.assertFalse(self.user_speaker.has_perm(ADD, self.system))
        self.assertFalse(self.user_any.has_perm(ADD, self.system))

    def test_change_speaker_list(self):
        CHANGE = self.p("CHANGE")
        self.assertTrue(self.user_meeting_moderator.has_perm(CHANGE, self.list))
        self.assertTrue(self.user_list_moderator.has_perm(CHANGE, self.list))
        self.assertFalse(self.user_speaker.has_perm(CHANGE, self.list))
        self.assertFalse(self.user_any.has_perm(CHANGE, self.list))

    def test_delete_speaker_list(self):
        DELETE = self.p("DELETE")
        self.assertTrue(self.user_meeting_moderator.has_perm(DELETE, self.list))
        self.assertTrue(self.user_list_moderator.has_perm(DELETE, self.list))
        self.assertFalse(self.user_speaker.has_perm(DELETE, self.list))
        self.assertFalse(self.user_any.has_perm(DELETE, self.list))

    def test_view_speaker_contextless(self):
        VIEW = self.p("VIEW")
        self.assertTrue(self.user_meeting_moderator.has_perm(VIEW, self.list))
        self.assertTrue(self.user_list_moderator.has_perm(VIEW, self.list))
        self.assertTrue(self.user_speaker.has_perm(VIEW, self.list))
        self.assertFalse(self.user_any.has_perm(VIEW, self.list))

    def test_view_speaker_meeting(self):
        VIEW = self.p("VIEW")
        self.assertTrue(self.user_list_moderator.has_perm(VIEW, self.list))
        self.assertTrue(self.user_speaker.has_perm(VIEW, self.list))
        self.assertFalse(self.user_any.has_perm(VIEW, self.list))
        self.assertTrue(self.user_proposer.has_perm(VIEW, self.list))


class SpeakerListSystemTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.room = cls.meeting.rooms.create()
        cls.system = cls.meeting.speaker_systems.create(
            method_name="simple", room=cls.room
        )
        cls.user_meeting_moderator = User.objects.create(username="m_moderator")
        cls.meeting.add_roles(cls.user_meeting_moderator, ROLE_MODERATOR)
        cls.user_list_moderator = User.objects.create(username="s_moderator")
        cls.system.add_roles(cls.user_list_moderator, ROLE_LIST_MODERATOR)
        cls.user_speaker = User.objects.create(username="in")
        cls.system.add_roles(cls.user_speaker, ROLE_SPEAKER)
        cls.user_any = User.objects.create(username="jane")
        cls.user_participant = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.user_participant, ROLE_PARTICIPANT)

    def setUp(self):
        self.system.refresh_from_db()
        self.meeting.refresh_from_db()

    def p(self, name):
        from voteit.speaker.permissions import SpeakerSystemPermissions

        return getattr(SpeakerSystemPermissions, name)

    def test_add_system(self):
        # FIXME We have no clue about contextless yet
        ADD = self.p("ADD")
        self.assertTrue(self.user_meeting_moderator.has_perm(ADD, self.room))
        self.assertFalse(self.user_list_moderator.has_perm(ADD, self.room))
        self.assertFalse(self.user_speaker.has_perm(ADD, self.room))
        self.assertFalse(self.user_any.has_perm(ADD, self.room))

    def test_change_system(self):
        CHANGE = self.p("CHANGE")
        self.assertIs(self.user_meeting_moderator.has_perm(CHANGE, self.system), True)
        self.assertIs(self.user_list_moderator.has_perm(CHANGE, self.system), False)
        self.assertIs(self.user_speaker.has_perm(CHANGE, self.system), False)
        self.assertIs(self.user_any.has_perm(CHANGE, self.system), False)

    def test_change_system_archived(self):
        CHANGE = self.p("CHANGE")
        self.system.archive()
        self.system.save()
        self.assertIs(self.user_meeting_moderator.has_perm(CHANGE, self.system), False)
        self.assertIs(self.user_list_moderator.has_perm(CHANGE, self.system), False)
        self.assertIs(self.user_speaker.has_perm(CHANGE, self.system), False)
        self.assertIs(self.user_any.has_perm(CHANGE, self.system), False)

    def test_manage_system(self):
        MANAGE = self.p("MANAGE")
        self.assertIs(self.user_meeting_moderator.has_perm(MANAGE, self.system), True)
        self.assertIs(self.user_list_moderator.has_perm(MANAGE, self.system), True)
        self.assertIs(self.user_speaker.has_perm(MANAGE, self.system), False)
        self.assertIs(self.user_any.has_perm(MANAGE, self.system), False)

    def test_manage_system_archived(self):
        MANAGE = self.p("MANAGE")
        self.system.archive()
        self.system.save()
        self.assertIs(self.user_meeting_moderator.has_perm(MANAGE, self.system), True)
        self.assertIs(self.user_list_moderator.has_perm(MANAGE, self.system), True)
        self.assertIs(self.user_speaker.has_perm(MANAGE, self.system), False)
        self.assertIs(self.user_any.has_perm(MANAGE, self.system), False)

    def test_delete_system(self):
        DELETE = self.p("DELETE")
        self.assertIs(self.user_meeting_moderator.has_perm(DELETE, self.system), True)
        self.assertIs(self.user_list_moderator.has_perm(DELETE, self.system), False)
        self.assertIs(self.user_speaker.has_perm(DELETE, self.system), False)
        self.assertIs(self.user_any.has_perm(DELETE, self.system), False)

    def test_view_system_meeting(self):
        VIEW = self.p("VIEW")
        self.assertIs(self.user_meeting_moderator.has_perm(VIEW, self.system), True)
        self.assertIs(self.user_list_moderator.has_perm(VIEW, self.system), True)
        self.assertIs(self.user_speaker.has_perm(VIEW, self.system), True)
        self.assertIs(self.user_any.has_perm(VIEW, self.system), False)


class SpeakerPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.room = cls.meeting.rooms.create()
        cls.system: SpeakerListSystem = cls.meeting.speaker_systems.create(
            method_name="simple",
            state="active",
            meeting_roles_to_speaker=[ROLE_PROPOSER],
            room=cls.room,
        )
        cls.user_meeting_moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.user_meeting_moderator, ROLE_MODERATOR)
        cls.user_list_moderator = User.objects.create(username="list_moderator")
        cls.system.add_roles(cls.user_list_moderator, ROLE_LIST_MODERATOR)
        cls.user_speaker = User.objects.create(username="in")
        cls.user_proposer = User.objects.create(username="proposer")
        cls.system.add_roles(cls.user_speaker, ROLE_SPEAKER)
        cls.meeting.add_roles(cls.user_proposer, ROLE_PROPOSER)
        cls.user_any = User.objects.create(username="jane")
        cls.list: SpeakerList = cls.system.speaker_lists.create()
        cls.system.active_list = cls.list
        cls.speaker = cls.list.speaker_items.create(user=cls.user_speaker)
        cls.system.save()

    def setUp(self):
        self.system.refresh_from_db()
        self.meeting.refresh_from_db()
        self.list.refresh_from_db()

    def p(self, name):
        from voteit.speaker.permissions import SpeakerPermissions

        return getattr(SpeakerPermissions, name)

    def test_add_speaker_list(self):
        ADD = self.p("ADD")
        self.assertTrue(self.user_meeting_moderator.has_perm(ADD, self.list))
        self.assertTrue(self.user_list_moderator.has_perm(ADD, self.list))
        self.assertFalse(self.user_speaker.has_perm(ADD, self.list))
        self.assertFalse(self.user_any.has_perm(ADD, self.list))

    def test_view_speaker(self):
        VIEW = self.p("VIEW")
        self.assertTrue(self.user_meeting_moderator.has_perm(VIEW, self.speaker))
        self.assertTrue(self.user_list_moderator.has_perm(VIEW, self.speaker))
        self.assertFalse(self.user_speaker.has_perm(VIEW, self.speaker))
        self.assertFalse(self.user_any.has_perm(VIEW, self.speaker))

    def test_change_speaker(self):
        CHANGE = self.p("CHANGE")
        self.assertTrue(self.user_meeting_moderator.has_perm(CHANGE, self.speaker))
        self.assertTrue(self.user_list_moderator.has_perm(CHANGE, self.speaker))
        self.assertFalse(self.user_speaker.has_perm(CHANGE, self.speaker))
        self.assertFalse(self.user_any.has_perm(CHANGE, self.speaker))

    def test_delete_speaker(self):
        DELETE = self.p("DELETE")
        self.assertTrue(self.user_meeting_moderator.has_perm(DELETE, self.speaker))
        self.assertTrue(self.user_list_moderator.has_perm(DELETE, self.speaker))
        self.assertFalse(self.user_speaker.has_perm(DELETE, self.speaker))
        self.assertFalse(self.user_any.has_perm(DELETE, self.speaker))
