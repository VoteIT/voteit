from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from voteit.agenda.models import AgendaItem
from voteit.agenda.models import LastRead
from voteit.agenda.messages import LastReadChanged

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class UpdateLastReadTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    def _mk_one(self, **kw):
        from voteit.agenda.messages import UpdateLastRead

        return UpdateLastRead({"user_pk": 2, "consumer_name": "abc"}, **kw)

    def test_message_job(self):
        msg = self._mk_one(agenda_item=1)
        response = msg.run_job()
        self.assertIsInstance(response, LastReadChanged)
        ai = AgendaItem.objects.get(pk=1)
        user = User.objects.get(pk=2)
        last_read = ai.last_read_set.filter(user=user).first()
        self.assertIsInstance(last_read, LastRead)

    @patch.object(LastReadChanged, "send_outgoing")
    def test_response_sent(self, mock_send):
        msg = self._mk_one(agenda_item=1)
        msg.run_job()
        self.assertTrue(mock_send.called)
