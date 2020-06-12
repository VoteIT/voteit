from django.test import TestCase
from django_fsm import has_transition_perm


class MotionProcessTests(TestCase):

    def setUp(self):
        from voteit.motion.models import MotionProcess
        self.mp = MotionProcess.objects.create()

    def _export_fixture(self):
        from voteit.meeting.models import Meeting
        self.jane = self.mp.movers.create(username="jane")
        self.tarzan = self.mp.movers.create(username="tarzan")
        self.m1 = self.mp.motions.create(author=self.jane, title="Equal rights for all", body="It's time for a change")
        self.m1.publish()
        self.m1.accept()
        self.m1.save()
        self.m1_p1 = self.m1.proposals.create(body="All men are created equal")
        self.m2 = self.mp.motions.create(author=self.tarzan, title="Ba na nas!", body="Bananas for monkeys!!1")
        self.m2.publish()
        self.m2.accept()
        self.m2.save()
        self.m2_p1 = self.m2.proposals.create(body="At least one banana for each monkey")
        self.meeting = Meeting.objects.create()

    def test_workflow_transitions(self):
        self.assertEqual("open", self.mp.state)
        self.mp.close()
        self.mp.open()
        self.mp.close()
        self.assertEqual("closed", self.mp.state)

    def test_transition_permissions(self):
        manager = self.mp.managers.create(username="manager")
        mover = self.mp.movers.create(username="mover")
        self.assertFalse(has_transition_perm(self.mp.open, mover))
        self.assertFalse(has_transition_perm(self.mp.close, mover))
        self.assertTrue(has_transition_perm(self.mp.open, manager))
        self.assertTrue(has_transition_perm(self.mp.close, manager))

    def test_get_selected_motions_qs(self):
        self._export_fixture()
        self.assertEqual([self.m1, self.m2], list(self.mp.get_selected_motions_qs().all()))
        self.m1.publish()
        self.m1.save()
        self.assertEqual([self.m2], list(self.mp.get_selected_motions_qs().all()))

    def test_populate_meeting(self):
        from voteit.proposal.models import Proposal
        self._export_fixture()
        self.mp.populate_meeting(self.meeting)
        self.assertEqual(
            ["Equal rights for all", "Ba na nas!"],
            [x.title for x in self.meeting.agenda_items.all()]
        )
        self.assertEqual(
            [self.jane, self.tarzan],
            [x.author for x in self.meeting.agenda_items.order_by("order").all()]
        )
        # Proposals
        qs = Proposal.objects.order_by("created")
        self.assertEqual(
            [self.jane, self.tarzan],
            [x.author for x in qs.all()]
        )
        self.assertEqual(
            ["All men are created equal", "At least one banana for each monkey"],
            [x.body for x in qs.all()]
        )

# FIXME: transition permission tests
