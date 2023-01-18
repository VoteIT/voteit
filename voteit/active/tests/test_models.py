from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from voteit.meeting.models import Meeting

User = get_user_model()


class ActiveUserTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.user = User.objects.create(username="abel")

    @property
    def _cut(self):
        from voteit.active.models import ActiveUser

        return ActiveUser

    def test_unique_per_meeeting(self):
        self._cut.objects.create(meeting=self.meeting, user=self.user)
        with self.assertRaises(IntegrityError):
            self._cut.objects.create(meeting=self.meeting, user=self.user)
