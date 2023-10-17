from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from voteit.agenda.models import AgendaItem
from voteit.meeting.models import Meeting
from voteit.room.models import Room
from voteit.speaker.models import SpeakerListSystem

User = get_user_model()


class RoomTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.ai: AgendaItem = cls.meeting.agenda_items.create()
        cls.user = User.objects.create(username="abel")
        cls.sls: SpeakerListSystem = SpeakerListSystem.objects.create(
            meeting=cls.meeting, method_name="simple"
        )
        cls.prop1 = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()

    @property
    def _cut(self):
        from voteit.room.models import Room

        return Room

    def test_constraint_blank_sls(self):
        instance = self._cut.objects.create(meeting=self.meeting)
        self.assertIsInstance(instance, self._cut)

    def test_constraint_sls_same(self):
        self._cut.objects.create(meeting=self.meeting, sls=self.sls)
        with self.assertRaises(IntegrityError):
            self._cut.objects.create(meeting=self.meeting, sls=self.sls)

    def test_constraint_sls_unset_no_block(self):
        one = self._cut.objects.create(meeting=self.meeting)
        two = self._cut.objects.create(meeting=self.meeting, sls=self.sls)
        three = self._cut.objects.create(meeting=self.meeting)

    def test_constraint_missmatching_meeting(self):
        new_meeting = Meeting.objects.create()
        with self.assertRaises(IntegrityError) as cm:
            self._cut.objects.create(meeting=new_meeting, sls=self.sls)
        self.assertEqual("SLS links to another meeting", str(cm.exception))


class HighlightProposalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.ai: AgendaItem = cls.meeting.agenda_items.create()
        cls.prop1 = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.prop3 = cls.ai.proposals.create()
        cls.room: Room = cls.meeting.rooms.create()

    @property
    def _cut(self):
        from voteit.room.models import HighlightProposal

        return HighlightProposal

    def test_dublicate(self):
        self._cut.objects.create(proposal=self.prop1, room=self.room)
        with self.assertRaises(IntegrityError):
            self._cut.objects.create(proposal=self.prop1, room=self.room)

    def test_auto_ordering(self):
        self.room.highlighted_proposals.create(proposal=self.prop2)
        self.room.highlighted_proposals.create(proposal=self.prop1)
        self.room.highlighted_proposals.create(proposal=self.prop3)
        self.assertEqual(
            [self.prop2.pk, self.prop1.pk, self.prop3.pk],
            list(self.room.highlighted_proposal_pks),
        )
