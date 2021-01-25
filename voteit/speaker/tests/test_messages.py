from django.contrib.auth import get_user_model
from django.test import TestCase
from voteit.messaging.errors import UnauthorizedError, NotFoundError

User = get_user_model()


class SpeakerListEnterTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        self.system = SpeakerListSystem.objects.create(method_name="simple")
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
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        self.system = SpeakerListSystem.objects.create(method_name="simple")
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


class ModeratorSpeakerListEnterTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        self.system = SpeakerListSystem.objects.create(method_name="simple")
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
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        self.system = SpeakerListSystem.objects.create(method_name="simple")
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
