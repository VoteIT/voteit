from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.meeting.utils import sort_agenda_items
from voteit.organisation.models import Organisation

User = get_user_model()


class MeetingSortTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.organisation: Organisation = Organisation.objects.get(pk=1)
        cls.ai_ae = cls.meeting.agenda_items.create(title="Är det så?")
        cls.ai_aa = cls.meeting.agenda_items.create(title="åhå")
        cls.ai_oe = cls.meeting.agenda_items.create(title="Öh")
        cls.ai_ae2 = cls.meeting.agenda_items.create(title="ärligt")
        cls.order_with_collation = [
            "Crisps",
            "Hot dogs",
            "Pickles",
            "åhå",
            "Är det så?",
            "ärligt",
            "Öh",
        ]

    def test_base_order(self):
        self.assertEqual(
            ["Pickles", "Crisps", "Hot dogs", "Är det så?", "åhå", "Öh", "ärligt"],
            list(self.meeting.agenda_items.values_list("title", flat=True)),
        )
        self.assertEqual(
            [1, 2, 3, 4, 5, 6, 7],
            list(self.meeting.agenda_items.values_list("order", flat=True)),
        )

    def test_reorder(self):
        qs = sort_agenda_items(self.meeting)

        self.assertEqual(
            self.order_with_collation,
            list(qs.values_list("title", flat=True)),
        )
        self.assertEqual(
            [2, 3, 1, 5, 4, 7, 6],
            list(qs.values_list("order", flat=True)),
        )

    def test_reorder_and_save(self):
        sort_agenda_items(self.meeting, reorder=True)
        qs = self.meeting.agenda_items.all()
        self.assertEqual(
            self.order_with_collation,
            list(qs.values_list("title", flat=True)),
        )
        self.assertEqual(
            [1, 2, 3, 4, 5, 6, 7],
            list(qs.values_list("order", flat=True)),
        )
