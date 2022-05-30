from django.test import TestCase

from voteit.core.testing import FakeCommit


class OnCommitLogger(TestCase):
    @property
    def _cut(self):
        from voteit.core.loggers import getOnCommitLogger

        return getOnCommitLogger

    def test_log_on_commit(self):
        with self.assertLogs("hello_world") as logs:
            # assertLogs checks for Logger class so adapters won't work, reinitialize
            logger = self._cut("hello_world")
            with FakeCommit():
                logger.info("Hello")
                self.assertEqual(0, len(logs.records))
            self.assertEqual(1, len(logs.records))
