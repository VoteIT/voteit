from logging import getLogger

from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch
from django.urls import reverse
from rest_framework.test import APITestCase


User = get_user_model()

logger = getLogger(__name__)


class RouterTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.participant = User.objects.get(username="participant")

    def get_urls(self):
        from voteit.core.rest_api.router import router

        for prefix, viewset, basename in router.registry:
            try:
                yield basename, viewset, reverse(basename + "-list")
            except NoReverseMatch:
                logger.warning(f"No reverse url match for {basename + '-list'}")

    def test_default_list_causes_no_exceptions(self):
        self.client.force_login(self.participant)
        for basename, viewset, url in self.get_urls():
            response = self.client.get(url)
            status = getattr(viewset, "expected_default_http_status", 200)
            self.assertEqual(
                status,
                response.status_code,
                f"API view {basename} must return HTTP 200. Class: {viewset.__module__}.{viewset.__name__}",
            )
