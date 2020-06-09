from django.contrib.auth.models import User
from django.test import TestCase


class RulesTests(TestCase):

    def setUp(self):
        from voteit.motion.models import MotionProcess
        self.mp = MotionProcess.objects.create()
        self.user = User.objects.create(username="a")

    def test_is_mp_participant(self):
        from voteit.motion.rules import is_mp_participant
        self.assertFalse(is_mp_participant(self.user, self.mp))
        self.mp.participants.add(self.user)
        self.mp.save()
        self.assertTrue(is_mp_participant(self.user, self.mp))

    def test_is_mp_mover(self):
        from voteit.motion.rules import is_mp_mover
        self.assertFalse(is_mp_mover(self.user, self.mp))
        self.mp.movers.add(self.user)
        self.mp.save()
        self.assertTrue(is_mp_mover(self.user, self.mp))

    def test_is_mp_manager(self):
        from voteit.motion.rules import is_mp_manager
        self.assertFalse(is_mp_manager(self.user, self.mp))
        self.mp.managers.add(self.user)
        self.mp.save()
        self.assertTrue(is_mp_manager(self.user, self.mp))
