from django.test import TestCase

from voteit.agenda.models import AgendaItem
from voteit.core.testing import mk_hashtag
from voteit.meeting.models import Meeting


class AgendaItemSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(
            body="Hello world", tags=["hello"]
        )

    def test_agenda_item(self):
        from voteit.agenda.rest_api.serializers import AgendaItemSerializer

        serializer = AgendaItemSerializer(self.ai)
        data = dict(serializer.data)
        self.assertTrue(data.pop("created"))
        self.assertTrue(data.pop("modified"))
        self.assertEqual(
            {
                "pk": self.ai.pk,
                "related_modified": None,
                "state": "private",
                "tags": ["hello"],
                "title": "",
                "body": "Hello world",
                "block_discussion": False,
                "block_proposals": False,
                "meeting": self.meeting.pk,
                "order": 0,
            },
            data,
        )

    def test_create_agenda_item_no_tags_from_body(self):
        from voteit.agenda.rest_api.serializers import CreateAgendaItemSerializer

        serializer = CreateAgendaItemSerializer(
            data={
                "meeting": self.meeting.pk,
                "body": f"Hello {mk_hashtag('world')}!",
                "tags": ["cheese"],
                "title": "Hello world!",
            }
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        instance = serializer.save()
        self.assertEqual(["cheese"], instance.tags)

    def test_agenda_item_body(self):
        from voteit.agenda.rest_api.serializers import AgendaItemBodySerializer

        serializer = AgendaItemBodySerializer(self.ai)
        data = dict(serializer.data)
        self.assertEqual(
            {
                "pk": self.ai.pk,
                "body": "Hello world",
            },
            data,
        )

    def test_agenda_item_list(self):
        from voteit.agenda.rest_api.serializers import AgendaItemListSerializer

        serializer = AgendaItemListSerializer(self.ai)
        data = dict(serializer.data)
        self.assertEqual(
            {
                "pk": self.ai.pk,
                "related_modified": None,
                "state": "private",
                "tags": ["hello"],
                "title": "",
                "block_discussion": False,
                "block_proposals": False,
                "meeting": self.meeting.pk,
                "order": 0,
            },
            data,
        )
