from django.contrib.auth.models import User
from django.test import TestCase

from voteit.motion.permissions import MotionPermissions as MP


class MotionProcessRulesTests(TestCase):

    def setUp(self):
        from voteit.motion.models import MotionProcess
        self.mp = MotionProcess.objects.create()
        self.any_user = User.objects.create(username="any")
        self.manager_user = self.mp.managers.create(username="manager")
        self.mover_user = self.mp.movers.create(username="mover")
        self.viewer_user = self.mp.viewer.create(username="viewer")  # FIXME

    def test_is_mp_viewer(self):
        from voteit.motion.rules import is_mp_viewer
        self.assertFalse(is_mp_viewer(self.any_user, self.mp))
        self.assertTrue(is_mp_viewer(self.viewer_user, self.mp))

    def test_is_mp_mover(self):
        from voteit.motion.rules import is_mp_mover
        self.assertFalse(is_mp_mover(self.any_user, self.mp))
        self.assertTrue(is_mp_mover(self.mover_user, self.mp))

    def test_is_mp_manager(self):
        from voteit.motion.rules import is_mp_manager
        self.assertFalse(is_mp_manager(self.any_user, self.mp))
        self.assertTrue(is_mp_manager(self.manager_user, self.mp))

    def test_can_add_motion(self):
        # Note this is tested against motion process
        # Check via user
        self.assertFalse(self.any_user.has_perm(MP.ADD, self.mp))
        self.assertFalse(self.mover_user.has_perm(MP.ADD, self.mp))
        self.assertTrue(self.manager_user.has_perm(MP.ADD, self.mp))
        # And open the process
        self.mp.open()
        self.assertFalse(self.any_user.has_perm(MP.ADD, self.mp))
        self.assertTrue(self.mover_user.has_perm(MP.ADD, self.mp))
        self.assertTrue(self.manager_user.has_perm(MP.ADD, self.mp))


class MotionRulesTests(TestCase):

    def setUp(self):
        from voteit.motion.models import MotionProcess
        self.mp = MotionProcess.objects.create()
        self.any_user = User.objects.create(username="any")
        self.manager_user = self.mp.managers.create(username="manager")
        self.mover_user = self.mp.movers.create(username="mover")
        self.viewer_user = self.mp.viewer.create(username="viewer")  # FIXME
        self.motion = self.mp.motions.create(author=self.mover_user)

    def test_can_manage_motion(self):
        self.assertFalse(self.any_user.has_perm(MP.MANAGE, self.motion))
        self.assertFalse(self.mover_user.has_perm(MP.MANAGE, self.motion))
        self.assertTrue(self.manager_user.has_perm(MP.MANAGE, self.motion))

    def test_can_submit_motion(self):
        self.assertFalse(self.any_user.has_perm(MP.SUBMIT, self.motion))
        self.assertFalse(self.mover_user.has_perm(MP.SUBMIT, self.motion))
        self.assertFalse(self.manager_user.has_perm(MP.SUBMIT, self.motion))  # Moderators publish!
        self.mp.open()  # No submissions allowed if it's not open
        self.assertFalse(self.any_user.has_perm(MP.SUBMIT, self.motion))
        self.assertTrue(self.mover_user.has_perm(MP.SUBMIT, self.motion))
        self.assertFalse(self.manager_user.has_perm(MP.SUBMIT, self.motion))  # Moderators publish!

    def test_can_retract_motion(self):
        self.assertFalse(self.any_user.has_perm(MP.RETRACT, self.motion))
        self.assertFalse(self.mover_user.has_perm(MP.RETRACT, self.motion))
        self.assertTrue(self.manager_user.has_perm(MP.RETRACT, self.motion))
        self.mp.open()
        self.assertFalse(self.any_user.has_perm(MP.RETRACT, self.motion))
        self.assertTrue(self.mover_user.has_perm(MP.RETRACT, self.motion))
        self.assertTrue(self.manager_user.has_perm(MP.RETRACT, self.motion))
        self.motion.submit()
        self.assertFalse(self.any_user.has_perm(MP.RETRACT, self.motion))
        self.assertTrue(self.mover_user.has_perm(MP.RETRACT, self.motion))
        self.assertTrue(self.manager_user.has_perm(MP.RETRACT, self.motion))
