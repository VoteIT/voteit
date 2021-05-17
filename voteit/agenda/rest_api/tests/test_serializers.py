from django.test import RequestFactory
from django.test import TestCase


class AgendaItemSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    @property
    def _cut(self):
        from voteit.agenda.rest_api.serializers import AgendaItemSerializer

        return AgendaItemSerializer

    # FIXME: Tests
