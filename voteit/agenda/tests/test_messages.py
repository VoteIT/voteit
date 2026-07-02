from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.agenda.messages import LastReadChangedSchema
from voteit.agenda.models import AgendaItem
from voteit.agenda.rest_api.serializers import LastReadSerializer

User = get_user_model()


class LastReadSerializerCompatTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    def test_compat_with_drf(self):
        user = User.objects.get(pk=2)
        ai = AgendaItem.objects.get(pk=1)
        last_read = ai.mark_read(user)
        serializer = LastReadSerializer(last_read)
        pydantics = LastReadChangedSchema(timestamp=last_read.timestamp, agenda_item=1)
        self.assertIsInstance(pydantics.timestamp, str)
        self.assertEqual(pydantics.timestamp, serializer.data["timestamp"])
