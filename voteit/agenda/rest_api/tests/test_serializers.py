from django.test import RequestFactory
from django.test import TestCase


class AgendaItemSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.agenda.models import AgendaItem

        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(
            body="Hello world", tags=["hello"]
        )

    @property
    def _cut(self):
        from voteit.agenda.rest_api.serializers import AgendaItemSerializer

        return AgendaItemSerializer

    def test_serialize(self):
        serializer = self._cut(self.ai)
        data = dict(serializer.data)
        self.assertTrue(data.pop("created"))
        self.assertTrue(data.pop("modified"))
        data.pop("id")
        self.assertEqual(
            {
                "pk": self.ai.pk,
                "related_modified": None,
                "state": "private",
                "tags": ["hello"],
                "mentions": [],
                "title": "",
                "block_discussion": False,
                "block_proposals": False,
                "body": "Hello world",
                "meeting": self.meeting.pk,
                "order": 0,
            },
            data,
        )
