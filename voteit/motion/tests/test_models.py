from django.test import TestCase


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

