from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.meeting.roles import ROLE_MODERATOR

User = get_user_model()


class SpeakerListTests(TestCase):
    def setUp(self):
        from voteit.speaker.roles import ROLE_SPEAKER, ROLE_LIST_MODERATOR
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        self.system = meeting.speaker_systems.create(
            method_name="simple", state="active"
        )
        self.user_moderator = User.objects.create(username="moderator")
        self.system.add_roles(self.user_moderator, ROLE_LIST_MODERATOR)
        self.user_speaker = User.objects.create(username="in")
        self.system.add_roles(self.user_speaker, ROLE_SPEAKER)
        self.user_any = User.objects.create(username="jane")
        self.list = self.system.speaker_lists.create()
        self.system.active_list = self.list
        self.system.save()

    def p(self, name):
        from voteit.speaker.permissions import SpeakerListPermissions

        return getattr(SpeakerListPermissions, name)

    def test_add_speaker_list(self):
        ADD = self.p("ADD")
        self.assertTrue(self.user_moderator.has_perm(ADD, self.system))
        self.assertFalse(self.user_speaker.has_perm(ADD, self.system))
        self.assertFalse(self.user_any.has_perm(ADD, self.system))

    def test_change_speaker_list(self):
        CHANGE = self.p("CHANGE")
        self.assertTrue(self.user_moderator.has_perm(CHANGE, self.list))
        self.assertFalse(self.user_speaker.has_perm(CHANGE, self.list))
        self.assertFalse(self.user_any.has_perm(CHANGE, self.list))

    def test_delete_speaker_list(self):
        DELETE = self.p("DELETE")
        self.assertTrue(self.user_moderator.has_perm(DELETE, self.list))
        self.assertFalse(self.user_speaker.has_perm(DELETE, self.list))
        self.assertFalse(self.user_any.has_perm(DELETE, self.list))

    def test_view_speaker_contextless(self):
        VIEW = self.p("VIEW")
        self.assertTrue(self.user_moderator.has_perm(VIEW, self.list))
        self.assertTrue(self.user_speaker.has_perm(VIEW, self.list))
        self.assertFalse(self.user_any.has_perm(VIEW, self.list))

    def test_view_speaker_meeting(self):
        VIEW = self.p("VIEW")
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        self.system.meeting = meeting
        self.system.save()
        meeting_participant = User.objects.create(username="participant")
        meeting.add_roles(meeting_participant, "participant")
        self.assertTrue(self.user_moderator.has_perm(VIEW, self.list))
        self.assertTrue(self.user_speaker.has_perm(VIEW, self.list))
        self.assertFalse(self.user_any.has_perm(VIEW, self.list))
        self.assertTrue(meeting_participant.has_perm(VIEW, self.list))

    def test_enter_speaker_list_open(self):
        ENTER = self.p("ENTER")
        self.assertTrue(self.user_moderator.has_perm(ENTER, self.list))
        self.assertTrue(self.user_speaker.has_perm(ENTER, self.list))
        self.assertFalse(self.user_any.has_perm(ENTER, self.list))

    def test_enter_speaker_list_closed(self):
        ENTER = self.p("ENTER")
        self.list.close()
        self.list.save()
        self.assertTrue(self.user_moderator.has_perm(ENTER, self.list))
        self.assertFalse(self.user_speaker.has_perm(ENTER, self.list))
        self.assertFalse(self.user_any.has_perm(ENTER, self.list))

    def test_leave_speaker_list_open(self):
        LEAVE = self.p("LEAVE")
        self.assertTrue(self.user_moderator.has_perm(LEAVE, self.list))
        self.assertTrue(self.user_speaker.has_perm(LEAVE, self.list))
        self.assertFalse(self.user_any.has_perm(LEAVE, self.list))

    def test_leave_currently_speaking(self):
        LEAVE = self.p("LEAVE")
        speaker = self.list.speaker_items.create(user=self.user_speaker)
        self.assertTrue(self.user_moderator.has_perm(LEAVE, self.list))
        self.assertTrue(self.user_speaker.has_perm(LEAVE, self.list))
        self.assertFalse(self.user_any.has_perm(LEAVE, self.list))
        self.list.current = speaker
        self.list.save()
        self.assertTrue(self.user_moderator.has_perm(LEAVE, self.list))
        self.assertFalse(self.user_speaker.has_perm(LEAVE, self.list))
        self.assertFalse(self.user_any.has_perm(LEAVE, self.list))

    def test_start(self):
        START = self.p("START")
        self.assertTrue(self.user_moderator.has_perm(START, self.list))
        self.assertFalse(self.user_speaker.has_perm(START, self.list))
        self.assertFalse(self.user_any.has_perm(START, self.list))

    def test_start_not_active_list(self):
        START = self.p("START")
        self.system.active_list = None
        self.system.save()
        self.assertFalse(self.user_moderator.has_perm(START, self.list))
        self.assertFalse(self.user_speaker.has_perm(START, self.list))
        self.assertFalse(self.user_any.has_perm(START, self.list))

    def test_stop(self):
        STOP = self.p("STOP")
        self.assertTrue(self.user_moderator.has_perm(STOP, self.list))
        self.assertFalse(self.user_speaker.has_perm(STOP, self.list))
        self.assertFalse(self.user_any.has_perm(STOP, self.list))

    def test_stop_not_active_list(self):
        STOP = self.p("STOP")
        self.system.active_list = None
        self.system.save()
        self.assertFalse(self.user_moderator.has_perm(STOP, self.list))
        self.assertFalse(self.user_speaker.has_perm(STOP, self.list))
        self.assertFalse(self.user_any.has_perm(STOP, self.list))


class SpeakerListSystemTests(TestCase):
    def setUp(self):
        from voteit.speaker.roles import ROLE_LIST_MODERATOR, ROLE_SPEAKER
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        self.system = meeting.speaker_systems.create(method_name="simple")
        self.user_meeting_moderator = User.objects.create(username="m_moderator")
        meeting.add_roles(self.user_meeting_moderator, ROLE_MODERATOR)
        self.user_moderator = User.objects.create(username="s_moderator")
        self.system.add_roles(self.user_moderator, ROLE_LIST_MODERATOR)
        self.user_speaker = User.objects.create(username="in")
        self.system.add_roles(self.user_speaker, ROLE_SPEAKER)
        self.user_any = User.objects.create(username="jane")

    def p(self, name):
        from voteit.speaker.permissions import SpeakerSystemPermissions

        return getattr(SpeakerSystemPermissions, name)

    def test_add_system(self):
        # FIXME We have no clue about contextless yet
        from voteit.meeting.models import Meeting

        ADD = self.p("ADD")
        meeting = Meeting.objects.create()
        self.system.meeting = meeting
        self.system.save()
        self.assertFalse(self.user_moderator.has_perm(ADD, meeting))
        self.assertFalse(self.user_speaker.has_perm(ADD, meeting))
        self.assertFalse(self.user_any.has_perm(ADD, meeting))
        meeting.add_roles(self.user_moderator, ROLE_MODERATOR)
        self.assertTrue(self.user_moderator.has_perm(ADD, meeting))

    def test_change_system(self):
        CHANGE = self.p("CHANGE")
        self.assertIs(self.user_meeting_moderator.has_perm(CHANGE, self.system), True)
        self.assertIs(self.user_moderator.has_perm(CHANGE, self.system), False)
        self.assertIs(self.user_speaker.has_perm(CHANGE, self.system), False)
        self.assertIs(self.user_any.has_perm(CHANGE, self.system), False)

    def test_delete_system(self):
        DELETE = self.p("DELETE")
        self.assertIs(self.user_meeting_moderator.has_perm(DELETE, self.system), True)
        self.assertIs(self.user_moderator.has_perm(DELETE, self.system), False)
        self.assertIs(self.user_speaker.has_perm(DELETE, self.system), False)
        self.assertIs(self.user_any.has_perm(DELETE, self.system), False)

    def test_view_system_contextless(self):
        VIEW = self.p("VIEW")
        self.assertTrue(self.user_moderator.has_perm(VIEW, self.system))
        self.assertTrue(self.user_speaker.has_perm(VIEW, self.system))
        self.assertFalse(self.user_any.has_perm(VIEW, self.system))

    def test_view_system_meeting(self):
        VIEW = self.p("VIEW")
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        self.system.meeting = meeting
        self.system.save()
        meeting_participant = User.objects.create(username="participant")
        meeting.add_roles(meeting_participant, "participant")
        self.assertTrue(self.user_moderator.has_perm(VIEW, self.system))
        self.assertTrue(self.user_speaker.has_perm(VIEW, self.system))
        self.assertFalse(self.user_any.has_perm(VIEW, self.system))
        self.assertTrue(meeting_participant.has_perm(VIEW, self.system))
