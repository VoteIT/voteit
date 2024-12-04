from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from envelope.testing import MessageCatcher
from envelope.testing import testing_channel_layers_setting

from voteit.agenda.messages import LastReadChangedSchema
from voteit.agenda.models import AgendaItem
from voteit.agenda.models import LastRead
from voteit.agenda.messages import LastReadChanged
from voteit.agenda.rest_api.serializers import LastReadSerializer

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class UpdateLastReadTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    def _mk_one(self, **kw):
        from voteit.agenda.messages import UpdateLastRead

        return UpdateLastRead(mm={"user_pk": 2, "consumer_name": "abc"}, **kw)

    def test_message_job(self):
        msg = self._mk_one(agenda_item=1)
        with MessageCatcher(LastReadChanged) as messages:
            msg.run_job()
        self.assertEqual(1, len(messages))
        response = messages[0]
        self.assertIsInstance(response, LastReadChanged)
        ai = AgendaItem.objects.get(pk=1)
        user = User.objects.get(pk=2)
        last_read = ai.last_read_set.filter(user=user).first()
        self.assertIsInstance(last_read, LastRead)

    def test_compat_with_drf(self):
        user = User.objects.get(pk=2)
        ai = AgendaItem.objects.get(pk=1)
        ai.mark_read(user)
        last_read = ai.last_read_set.filter(user=user).first()
        serializer = LastReadSerializer(last_read)
        pydantics = LastReadChangedSchema(timestamp=last_read.timestamp, agenda_item=1)
        self.assertIsInstance(pydantics.timestamp, str)
        self.assertEqual(pydantics.timestamp, serializer.data["timestamp"])
