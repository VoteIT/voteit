from django.contrib.auth.models import User
from django.test import TestCase

from voteit.motion.permissions import MotionPermissions as MP
from voteit.motion.permissions import MotionProcessPermissions as MPP


class MotionProcessRulesTests(TestCase):

    def setUp(self):
        from voteit.motion.models import MotionProcess
        from voteit.motion.roles import MPManager
        from voteit.motion.roles import MPMover
        self.mp = MotionProcess.objects.create()
        self.any_user = User.objects.create(username="any")
        self.manager_user = self.mp.managers.create(username="manager")
        MPManager(self.mp).add(self.manager_user)  # Make sure required roles happen
        self.mover_user = self.mp.movers.create(username="mover")
        MPMover(self.mp).add(self.mover_user)
        self.viewer_user = self.mp.viewer.create(username="viewer")

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
        self.assertFalse(self.any_user.has_perm(MP.ADD, self.mp))
        self.assertTrue(self.mover_user.has_perm(MP.ADD, self.mp))
        self.assertTrue(self.manager_user.has_perm(MP.ADD, self.mp))
        # And close the process
        self.mp.close()
        self.assertFalse(self.any_user.has_perm(MP.ADD, self.mp))
        self.assertFalse(self.mover_user.has_perm(MP.ADD, self.mp))
        self.assertTrue(self.manager_user.has_perm(MP.ADD, self.mp))

    def test_can_view_motion_process_public(self):
        self.mp.public = True
        self.mp.save()
        self.assertTrue(self.any_user.has_perm(MPP.VIEW, self.mp))
        self.assertTrue(self.viewer_user.has_perm(MPP.VIEW, self.mp))
        self.assertTrue(self.mover_user.has_perm(MPP.VIEW, self.mp))
        self.assertTrue(self.manager_user.has_perm(MPP.VIEW, self.mp))
        # And close the process
        self.mp.close()
        self.assertTrue(self.any_user.has_perm(MPP.VIEW, self.mp))
        self.assertTrue(self.viewer_user.has_perm(MPP.VIEW, self.mp))
        self.assertTrue(self.mover_user.has_perm(MPP.VIEW, self.mp))
        self.assertTrue(self.manager_user.has_perm(MPP.VIEW, self.mp))

    def test_can_view_motion_process_private(self):
        self.assertFalse(self.any_user.has_perm(MPP.VIEW, self.mp))
        self.assertTrue(self.viewer_user.has_perm(MPP.VIEW, self.mp))
        self.assertTrue(self.mover_user.has_perm(MPP.VIEW, self.mp))
        self.assertTrue(self.manager_user.has_perm(MPP.VIEW, self.mp))
        # And close the process
        self.mp.close()
        self.assertFalse(self.any_user.has_perm(MPP.VIEW, self.mp))
        self.assertTrue(self.viewer_user.has_perm(MPP.VIEW, self.mp))
        self.assertTrue(self.mover_user.has_perm(MPP.VIEW, self.mp))
        self.assertTrue(self.manager_user.has_perm(MPP.VIEW, self.mp))


class MotionRulesTests(TestCase):

    def setUp(self):
        from voteit.motion.models import MotionProcess
        from voteit.motion.roles import MPManager
        from voteit.motion.roles import MPMover
        self.mp = MotionProcess.objects.create()
        self.any_user = User.objects.create(username="any")
        self.manager_user = self.mp.managers.create(username="manager")
        MPManager(self.mp).add(self.manager_user)  # Handle required roles
        self.mover_user = self.mp.movers.create(username="mover")
        self.mover_other_user = self.mp.movers.create(username="other_mover")
        MPMover(self.mp).add(self.mover_user, self.mover_other_user)
        self.viewer_user = self.mp.viewer.create(username="viewer")
        self.motion = self.mp.motions.create(author=self.mover_user)

    def test_can_change_motion(self):
        self.assertFalse(self.any_user.has_perm(MP.CHANGE, self.motion))
        self.assertTrue(self.mover_user.has_perm(MP.CHANGE, self.motion))
        self.assertTrue(self.manager_user.has_perm(MP.CHANGE, self.motion))
        self.motion.submit()
        self.assertFalse(self.any_user.has_perm(MP.CHANGE, self.motion))
        self.assertFalse(self.mover_user.has_perm(MP.CHANGE, self.motion))
        self.assertTrue(self.manager_user.has_perm(MP.CHANGE, self.motion))
        self.mp.close()
        self.assertFalse(self.any_user.has_perm(MP.CHANGE, self.motion))
        self.assertFalse(self.mover_user.has_perm(MP.CHANGE, self.motion))
        self.assertTrue(self.manager_user.has_perm(MP.CHANGE, self.motion))

    def test_can_manage_motion(self):
        self.assertFalse(self.any_user.has_perm(MP.MANAGE, self.motion))
        self.assertFalse(self.mover_user.has_perm(MP.MANAGE, self.motion))
        self.assertTrue(self.manager_user.has_perm(MP.MANAGE, self.motion))

    def test_can_view_motion_public(self):
        self.mp.public = True
        self.mp.save()
        self.assertFalse(self.any_user.has_perm(MP.VIEW, self.motion))
        self.assertTrue(self.mover_user.has_perm(MP.VIEW, self.motion))
        self.assertFalse(self.mover_other_user.has_perm(MP.VIEW, self.motion))
        self.assertTrue(self.manager_user.has_perm(MP.VIEW, self.motion))
        # And publish the motion
        self.motion.publish()
        self.assertTrue(self.any_user.has_perm(MP.VIEW, self.motion))
        self.assertTrue(self.mover_user.has_perm(MP.VIEW, self.motion))
        self.assertTrue(self.mover_other_user.has_perm(MP.VIEW, self.motion))
        self.assertTrue(self.manager_user.has_perm(MP.VIEW, self.motion))

    def test_can_view_motion_private(self):
        self.assertFalse(self.any_user.has_perm(MP.VIEW, self.motion))
        self.assertTrue(self.mover_user.has_perm(MP.VIEW, self.motion))
        self.assertFalse(self.mover_other_user.has_perm(MP.VIEW, self.motion))
        self.assertTrue(self.manager_user.has_perm(MP.VIEW, self.motion))
        # And publish
        self.motion.publish()
        self.assertFalse(self.any_user.has_perm(MP.VIEW, self.motion))
        self.assertTrue(self.mover_user.has_perm(MP.VIEW, self.motion))
        self.assertTrue(self.mover_other_user.has_perm(MP.VIEW, self.motion))
        self.assertTrue(self.manager_user.has_perm(MP.VIEW, self.motion))

    def test_can_submit_motion(self):
        self.assertFalse(self.any_user.has_perm(MP.SUBMIT, self.motion))
        self.assertTrue(self.mover_user.has_perm(MP.SUBMIT, self.motion))
        self.assertFalse(self.manager_user.has_perm(MP.SUBMIT, self.motion))  # Moderators publish!
        self.mp.close()  # No submissions allowed if it's not open
        self.assertFalse(self.any_user.has_perm(MP.SUBMIT, self.motion))
        self.assertFalse(self.mover_user.has_perm(MP.SUBMIT, self.motion))
        self.assertFalse(self.manager_user.has_perm(MP.SUBMIT, self.motion))  # Moderators publish!

    def test_can_retract_motion(self):
        self.assertFalse(self.any_user.has_perm(MP.RETRACT, self.motion))
        self.assertTrue(self.mover_user.has_perm(MP.RETRACT, self.motion))
        self.assertTrue(self.manager_user.has_perm(MP.RETRACT, self.motion))
        self.motion.submit()
        self.assertFalse(self.any_user.has_perm(MP.RETRACT, self.motion))
        self.assertTrue(self.mover_user.has_perm(MP.RETRACT, self.motion))
        self.assertTrue(self.manager_user.has_perm(MP.RETRACT, self.motion))
        self.mp.close()
        self.assertFalse(self.any_user.has_perm(MP.RETRACT, self.motion))
        self.assertFalse(self.mover_user.has_perm(MP.RETRACT, self.motion))
        self.assertTrue(self.manager_user.has_perm(MP.RETRACT, self.motion))
