from django.test import TestCase

# Create your tests here.


class AgendaItemTests(TestCase):

    #def setUp(self):
    #    pass

    @property
    def _cut(self):
        from voteit.agenda.models import AgendaItem
        return AgendaItem

    def test_meeting_relation(self):
        from voteit.meeting.models import Meeting
        meeting = Meeting.objects.create(title="Hello world")
        obj = self._cut.objects.create(meeting=meeting)
        self.assertEqual(obj.meeting, meeting)
        self.assertEqual(obj, meeting.agenda_items.all()[0])
        meeting.delete()
        self.assertEqual(0, self._cut.objects.count())

