from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from voteit.messaging.errors import UnauthorizedError, NotFoundError, ValidationErrorMsg

User = get_user_model()


class SpeakerListEnterTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        self.system = SpeakerListSystem.objects.create(
            method_name="simple", active=True
        )
        self.list = SpeakerList.objects.create(list_system=self.system)
        self.user = User.objects.create(username="jane")
        self.system.add_roles(self.user, "speaker")

    @property
    def _cut(self):
        from voteit.speaker.messages import SpeakerListEnter

        return SpeakerListEnter

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.list.pk)
        return self._cut({"user_pk": self.user.pk, "consumer_name": "abc"}, **kw)

    def test_enter(self):
        self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        msg.run_job()
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())

    def test_enter_already_in_list(self):
        from voteit.messaging.messages.text import TextResponse

        self.list.speaker_items.create(user=self.user)
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        response = msg.run_job()
        self.assertIsInstance(response, TextResponse)

    def test_enter_closed_list(self):
        self.list.close()
        self.list.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)


class SpeakerListLeaveTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        self.system = SpeakerListSystem.objects.create(method_name="simple")
        self.list = SpeakerList.objects.create(list_system=self.system)
        self.user = User.objects.create(username="jane")
        self.system.add_roles(self.user, "speaker")
        self.speaker = self.list.speaker_items.create(user=self.user)

    @property
    def _cut(self):
        from voteit.speaker.messages import SpeakerListLeave

        return SpeakerListLeave

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.list.pk)
        return self._cut({"user_pk": self.user.pk, "consumer_name": "abc"}, **kw)

    def test_leave(self):
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        msg.run_job()
        self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())

    def test_leave_not_in_list(self):
        from voteit.messaging.messages.text import TextResponse

        self.speaker.delete()
        self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        response = msg.run_job()
        self.assertIsInstance(response, TextResponse)

    def test_leave_with_old_entry(self):
        self.speaker.order = None
        self.speaker.save()
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        msg.run_job()
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())


class SpeakerListSetActiveTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerList
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        self.system = meeting.speaker_systems.create(method_name="simple", active=True)
        self.list = SpeakerList.objects.create(list_system=self.system)
        self.user = User.objects.create(username="jane")
        self.system.add_roles(self.user, "list_moderator")

    @property
    def _cut(self):
        from voteit.speaker.messages import SetActiveList

        return SetActiveList

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.list.pk)
        return self._cut({"user_pk": self.user.pk, "consumer_name": "abc"}, **kw)

    def test_set_active(self):
        from voteit.messaging.messages.text import TextResponse

        msg = self._mk_one()
        response = msg.run_job()
        self.assertIsInstance(response, TextResponse)
        self.system.refresh_from_db()
        self.assertEqual(self.system.active_list, self.list)

    def test_set_active_already_active(self):
        self.system.active_list = self.list
        self.system.save()
        msg = self._mk_one()
        response = msg.run_job()
        self.assertIsNone(response)

    def test_set_active_another_list_has_current_speaker(self):
        other_list = self.system.speaker_lists.create()
        self.system.active_list = other_list
        self.system.save()
        other_speaker = other_list.speaker_items.create(user=self.user)
        other_list.start_speaker(other_speaker)
        msg = self._mk_one()
        self.assertRaises(ValidationErrorMsg, msg.run_job)


class StartSpeakerInListTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerList
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        self.system = meeting.speaker_systems.create(method_name="simple", active=True)
        self.list = SpeakerList.objects.create(list_system=self.system)
        self.system.active_list = self.list
        self.system.save()
        self.user = User.objects.create(username="jane")
        self.speaker = self.list.speaker_items.create(user=self.user)
        self.moderator = User.objects.create(username="moderator")
        self.system.add_roles(self.user, "speaker")
        self.system.add_roles(self.moderator, "list_moderator")

    @property
    def _cut(self):
        from voteit.speaker.messages import StartSpeakerInList

        return StartSpeakerInList

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.list.pk)
        kw.setdefault("userid", self.user.pk)
        return self._cut({"user_pk": self.moderator.pk, "consumer_name": "abc"}, **kw)

    def test_start_speaker(self):
        self.assertIsNone(self.list.current)
        msg = self._mk_one()
        msg.run_job()
        self.list.refresh_from_db()
        self.assertIsNotNone(self.list.current)
        self.speaker.refresh_from_db()
        self.assertIsInstance(self.speaker.started, datetime)
        self.assertEqual(self.list.current, self.speaker)

    def test_start_speaker_already_started(self):
        self.list.start_speaker(self.speaker)
        self.assertIsNotNone(self.list.current)
        msg = self._mk_one()
        self.assertRaises(ValidationErrorMsg, msg.run_job)

    def test_start_speaker_someone_else_speaking(self):
        new_user = User.objects.create(username="new_speaker")
        new_speaker = self.list.speaker_items.create(user=new_user)
        self.list.start_speaker(new_speaker)
        self.assertEqual(new_speaker, self.list.current)
        msg = self._mk_one()
        msg.run_job()
        self.list.refresh_from_db()
        self.assertEqual(self.speaker, self.list.current)

    def test_start_speaker_not_active_list(self):
        self.system.active_list = None
        self.system.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)


class StopSpeakerInListTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerList
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        self.system = meeting.speaker_systems.create(method_name="simple", active=True)
        self.list = SpeakerList.objects.create(list_system=self.system)
        self.system.active_list = self.list
        self.system.save()
        self.user = User.objects.create(username="jane")
        self.speaker = self.list.speaker_items.create(user=self.user)
        self.list.start_speaker(self.speaker)
        self.list.refresh_from_db()
        self.moderator = User.objects.create(username="moderator")
        self.system.add_roles(self.user, "speaker")
        self.system.add_roles(self.moderator, "list_moderator")

    @property
    def _cut(self):
        from voteit.speaker.messages import StopSpeakerInList

        return StopSpeakerInList

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.list.pk)
        kw.setdefault("userid", self.user.pk)
        return self._cut({"user_pk": self.moderator.pk, "consumer_name": "abc"}, **kw)

    def test_stop_speaker(self):
        msg = self._mk_one()
        msg.run_job()
        self.list.refresh_from_db()
        self.speaker.refresh_from_db()
        self.assertIsNone(self.list.current)
        self.assertEqual(1, self.speaker.seconds)

    def test_stop_speaker_no_current_speaker(self):
        self.list.stop_speaker()
        msg = self._mk_one()
        self.assertRaises(ValidationErrorMsg, msg.run_job)

    def test_stop_speaker_another_speaker_is_active(self):
        nonspeaking_user = self.list.speakers.create(username="falsy")
        msg = self._mk_one(userid=nonspeaking_user.pk)
        self.assertRaises(ValidationErrorMsg, msg.run_job)


class ModeratorSpeakerListEnterTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerList
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        self.system = meeting.speaker_systems.create(method_name="simple", active=True)
        self.list = SpeakerList.objects.create(list_system=self.system)
        self.user = User.objects.create(username="jane")
        self.moderator = User.objects.create(username="moderator")
        self.system.add_roles(self.user, "speaker")
        self.system.add_roles(self.moderator, "list_moderator")

    @property
    def _cut(self):
        from voteit.speaker.messages import ModeratorSpeakerListEnter

        return ModeratorSpeakerListEnter

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.list.pk)
        kw.setdefault("userid", self.user.pk)
        return self._cut({"user_pk": self.moderator.pk, "consumer_name": "abc"}, **kw)

    def test_enter(self):
        self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        msg.run_job()
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())

    def test_enter_already_in_list(self):
        from voteit.messaging.messages.text import TextResponse

        self.list.speaker_items.create(user=self.user)
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        response = msg.run_job()
        self.assertIsInstance(response, TextResponse)

    def test_enter_closed_list(self):
        self.list.close()
        self.list.save()
        msg = self._mk_one()
        msg.run_job()
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())

    def test_enter_wrong_userid(self):
        msg = self._mk_one(userid=-1)
        self.assertRaises(NotFoundError, msg.run_job)


class ModeratorSpeakerListLeaveTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerList
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        self.system = meeting.speaker_systems.create(method_name="simple", active=True)
        self.list = SpeakerList.objects.create(list_system=self.system)
        self.user = User.objects.create(username="jane")
        self.system.add_roles(self.user, "speaker")
        self.speaker = self.list.speaker_items.create(user=self.user)
        self.moderator = User.objects.create(username="moderator")
        self.system.add_roles(self.user, "speaker")
        self.system.add_roles(self.moderator, "list_moderator")

    @property
    def _cut(self):
        from voteit.speaker.messages import ModeratorSpeakerListLeave

        return ModeratorSpeakerListLeave

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.list.pk)
        kw.setdefault("userid", self.user.pk)
        return self._cut({"user_pk": self.moderator.pk, "consumer_name": "abc"}, **kw)

    def test_leave(self):
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        msg.run_job()
        self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())

    def test_leave_not_in_list(self):
        from voteit.messaging.messages.text import TextResponse

        self.speaker.delete()
        self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        response = msg.run_job()
        self.assertIsInstance(response, TextResponse)

    def test_leave_with_old_entry(self):
        self.speaker.order = None
        self.speaker.save()
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        msg.run_job()
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
