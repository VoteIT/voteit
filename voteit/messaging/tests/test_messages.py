from unittest import mock
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from django_rq import get_queue
from fakeredis import FakeRedis
from rq import SimpleWorker

from voteit.core.queues import TESTING_QUEUE
from voteit.messaging.errors import JobError

User = get_user_model()

_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class DeferredJobTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="helloer")

    def setUp(self):
        self.fakeredis_conn = FakeRedis()
        self.queue = get_queue(
            TESTING_QUEUE, autocommit=True, connection=self.fakeredis_conn
        )

    def _mk_worker(self):
        # We may want to add all the optional worker classes from settings here
        return SimpleWorker(
            queues=[self.queue],
            connection=self.fakeredis_conn,
            disable_default_exception_handler=True,
            # log_job_description=False,
        )

    def test_translation(self):
        from voteit.messaging.messages.testing import HelloResponse
        from voteit.messaging.jobs import run_job

        HelloResponse.from_message = mocked = mock.MagicMock()
        run_job(
            {},
            {"language": "sv", "type": "testing.hello", "user_pk": self.user.pk},
            incoming=True,
            atomic=False,
        )

        self.assertTrue(mocked.called)
        self.assertEqual("Hej helloer!", mocked.mock_calls[0].kwargs.get("greeting"))

    @patch.object(JobError, "send_outgoing")
    def test_failing_job(self, mock_send):

        from voteit.messaging.messages.testing import BadJob

        badjob = BadJob(mm={"consumer_name": "abc", "message_id": "1"})
        badjob.enqueue(queue=self.queue)
        worker = self._mk_worker()
        completed = worker.work(burst=True)
        self.assertTrue(completed)
        self.assertTrue(mock_send.called)
