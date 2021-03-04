from django.db import IntegrityError
from django.test import TestCase


class PresenceCheckTests(TestCase):
    def setUp(self):
        from voteit.presence.models import PresenceSystem

        self.system: PresenceSystem = PresenceSystem.objects.create()

    def test_save_duplicate(self):
        first = self.system.presence_checks.create()
        # Updating should of course not complain
        first.close()
        first.save()
        # This is open
        second = self.system.presence_checks.create()
        # Another open not ok
        self.assertRaises(IntegrityError, self.system.presence_checks.create)
