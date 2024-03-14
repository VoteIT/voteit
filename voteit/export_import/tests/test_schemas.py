import json

from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.export_import.tests import read_fixture


class ExportImportMeetingTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture", "full_ai_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)

    @property
    def _cut(self):
        from voteit.export_import.schemas import MeetingStructure

        return MeetingStructure

    def test_export_json_roundtrip(self):
        data = self._cut.from_orm(self.meeting)
        json_data = data.json()
        json.loads(json_data)

    def test_import(self):
        import_dict = read_fixture("combined_meeting_fixture.yaml")
        data = self._cut(**import_dict)
        self.assertEqual(self.meeting.agenda_items.count(), len(data.agenda_items))

    def test_import_export_cmp(self):
        import_dict = read_fixture("combined_meeting_fixture.yaml")
        import_data = self._cut(**import_dict)
        export_data = self._cut.from_orm(self.meeting)
        self.assertEqual(import_data, export_data)
        import_agenda_data = import_data.agenda_items[0].dict()
        export_agenda_data = export_data.agenda_items[0].dict()
        self.assertEqual(import_agenda_data, export_agenda_data)
