import django_rq
from django.conf import settings
from django.test.runner import DiscoverRunner
from django.test.utils import override_settings

#: Redis db the test queues use. No worker listens on it, and it's flushed on start.
TEST_RQ_DB = 15


class VoteITTestRunner(DiscoverRunner):
    """Keeps tests off the developer's redis: cache (and with it cache-backed
    sessions) and channel layer become in-process, RQ moves to its own db.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._redis_override = override_settings(
            CACHES={
                "default": {
                    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                    "LOCATION": "voteit-tests",
                }
            },
            CHANNEL_LAYERS={
                "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
            },
            RQ_QUEUES={
                name: {**conf, "DB": TEST_RQ_DB}
                for name, conf in settings.RQ_QUEUES.items()
            },
        )
        self._redis_override.enable()
        django_rq.get_connection("default").flushdb()

    def teardown_test_environment(self, **kwargs):
        self._redis_override.disable()
        super().teardown_test_environment(**kwargs)
