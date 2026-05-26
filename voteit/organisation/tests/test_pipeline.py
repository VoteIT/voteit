from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.organisation.models import Organisation
from voteit.organisation.pipeline import ensure_userid

User = get_user_model()


class EnsureUseridTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()

    def _make_user(self, **kwargs):
        return self.org.users.create(**kwargs)

    def test_skips_when_no_user(self):
        ensure_userid(backend=None, user=None)

    def test_skips_when_userid_already_set(self):
        user = self._make_user(username="already", userid="existing-id")
        ensure_userid(backend=None, user=user)
        user.refresh_from_db()
        self.assertEqual("existing-id", user.userid)

    def test_sets_userid_from_name(self):
        user = self._make_user(username="anna", first_name="Anna", last_name="Karlsson")
        self.assertIsNone(user.userid)
        ensure_userid(backend=None, user=user)
        user.refresh_from_db()
        self.assertEqual("anna-karlsson", user.userid)

    def test_deduplicates_userid(self):
        self._make_user(username="taken", userid="anna-karlsson")
        user = self._make_user(username="anna2", first_name="Anna", last_name="Karlsson")
        ensure_userid(backend=None, user=user)
        user.refresh_from_db()
        self.assertIsNotNone(user.userid)
        self.assertNotEqual("anna-karlsson", user.userid)
        self.assertTrue(user.userid.startswith("anna-karlsson-"))

    def test_skips_when_name_cannot_be_slugified(self):
        # A user with no name produces an empty slug, so generate returns None
        user = self._make_user(username="noname")
        ensure_userid(backend=None, user=user)
        user.refresh_from_db()
        self.assertIsNone(user.userid)
