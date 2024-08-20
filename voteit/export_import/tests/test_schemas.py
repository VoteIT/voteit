import json

from django.test import TestCase

from voteit.agenda.rest_api.serializers import AgendaItemSerializer
from voteit.discussion.rest_api.serializers import DiscussionPostDetailSerializer
from voteit.meeting.models import Meeting
from voteit.export_import.tests import read_fixture
from voteit.meeting.rest_api.serializers import MeetingGroupSerializer
from voteit.proposal.rest_api.serializers import DiffProposalDetailSerializer
from voteit.proposal.rest_api.serializers import GenericProposalSerializer
from voteit.proposal.rest_api.serializers import ProposalDetailSerializer
from voteit.proposal.rest_api.serializers import TextDocumentSerializer


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


class SchemasMatchCommonSerializersTests(TestCase):
    """
    Make sure we haven't missed any new feature of models when we export/import
    """

    fixtures = ["meeting_test_fixture", "agenda_test_fixture", "full_ai_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.export_import.schemas import MeetingStructure

        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.export_data: MeetingStructure = MeetingStructure.from_orm(cls.meeting)
        cls.proposals = tuple(
            cls.meeting.agenda_items.first().proposals.all().select_subclasses()
        )

    def test_serializer_to_schema_for_ai(self):
        serializer = AgendaItemSerializer(self.meeting.agenda_items.all(), many=True)
        self.assertEqual(3, len(serializer.data))
        self.assertSetEqual(
            {
                x
                for x in serializer.data[0]
                if x not in {"pk", "order", "meeting", "related_modified"}
            },
            set(
                self.export_data.agenda_items[0].dict(
                    exclude={"text_documents", "proposals", "discussions"}
                )
            ),
        )

    def test_serializer_to_schema_for_group(self):
        serializer = MeetingGroupSerializer(self.meeting.groups.all(), many=True)
        self.assertEqual(1, len(serializer.data))
        self.assertSetEqual(
            {x for x in serializer.data[0] if x not in {"pk", "meeting"}},
            set(
                self.export_data.groups[0].dict(
                    exclude={"members", "created", "modified"}
                )
            ),
        )

    def test_serializer_to_schema_for_text_document(self):
        serializer = TextDocumentSerializer(
            self.meeting.agenda_items.first().text_documents.all(), many=True
        )
        self.assertEqual(1, len(serializer.data))
        # Paragraphs aren't needed within the export, since it's basically duplicate information
        self.assertSetEqual(
            {
                x
                for x in serializer.data[0]
                if x not in {"pk", "agenda_item", "paragraphs"}
            },
            set(self.export_data.agenda_items[0].text_documents[0].dict()),
        )

    def test_serializer_to_schema_for_proposal(self):
        serializer = GenericProposalSerializer(self.proposals[1])
        self.assertIsInstance(serializer, ProposalDetailSerializer)
        # FIXME: Mentions
        self.assertSetEqual(
            {
                x
                for x in serializer.data
                if x not in {"pk", "agenda_item", "shortname", "mentions"}
            },
            set(self.export_data.agenda_items[0].proposals[1].dict()),
        )

    def test_serializer_to_schema_for_diff_proposal(self):
        serializer = GenericProposalSerializer(self.proposals[0])
        self.assertIsInstance(serializer, DiffProposalDetailSerializer)
        # FIXME: Mentions
        self.assertSetEqual(
            {
                x
                for x in serializer.data
                if x
                not in {"pk", "agenda_item", "shortname", "mentions", "body_diff_brief"}
            },
            set(
                self.export_data.agenda_items[0]
                .proposals[0]
                .dict(exclude={"text_document"})
            ),
        )

    def test_serializer_to_schema_for_discusion_post(self):
        serializer = DiscussionPostDetailSerializer(
            self.meeting.agenda_items.first().discussions.all(), many=True
        )
        self.assertEqual(2, len(serializer.data))
        # FIXME: Mentions
        self.assertSetEqual(
            {
                x
                for x in serializer.data[0]
                if x not in {"pk", "agenda_item", "mentions"}
            },
            set(
                self.export_data.agenda_items[0]
                .discussions[0]
                .dict(exclude={"modified"})
            ),
        )
