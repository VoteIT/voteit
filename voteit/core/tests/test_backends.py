from django.test import TestCase

from voteit.core.backends import PrefetchedModelBackend
from voteit.core.models import User
from voteit.organisation.models import Organisation


class PrefetchedModelBackendTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()
        cls.user = User.objects.create_user(
            username="testuser", password="secret", organisation=cls.org
        )
        cls.backend = PrefetchedModelBackend()

    def test_get_user_prefetches_organisation(self):
        user = self.backend.get_user(self.user.pk)
        with self.assertNumQueries(0):
            _ = user.organisation.pk

    def test_get_user_returns_none_for_missing(self):
        self.assertIsNone(self.backend.get_user(-1))

    async def test_aget_user_prefetches_organisation(self):
        user = await self.backend.aget_user(self.user.pk)
        self.assertIn("organisation", user._state.fields_cache)

    async def test_aget_user_returns_none_for_missing(self):
        self.assertIsNone(await self.backend.aget_user(-1))
