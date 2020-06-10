from django.test import TestCase
from django_fsm import has_transition_perm


class MotionProcessTests(TestCase):

    def setUp(self):
        from voteit.motion.models import MotionProcess
        self.mp = MotionProcess.objects.create()

    def test_workflow_transitions(self):
        self.assertEqual("private", self.mp.state)
        self.mp.open()
        self.mp.close()
        self.mp.private()
        self.mp.open()
        self.assertEqual("open", self.mp.state)

    def test_transition_permissions(self):
        manager = self.mp.managers.create(username="manager")
        mover = self.mp.movers.create(username="mover")
        self.assertFalse(has_transition_perm(self.mp.open, mover))
        self.assertFalse(has_transition_perm(self.mp.close, mover))
        self.assertFalse(has_transition_perm(self.mp.private, mover))
        self.assertTrue(has_transition_perm(self.mp.open, manager))
        self.assertTrue(has_transition_perm(self.mp.close, manager))
        self.assertTrue(has_transition_perm(self.mp.private, manager))


# FIXME: transition permission tests
