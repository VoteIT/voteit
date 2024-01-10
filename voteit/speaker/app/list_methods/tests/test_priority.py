from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.timezone import now

from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem

User = get_user_model()


class PriorityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.system = SpeakerListSystem.objects.create(method_name="priority")
        cls.speaker_list = SpeakerList.objects.create(speaker_system=cls.system)
        cls.user_one = User.objects.create(username="one")
        cls.user_two = User.objects.create(username="two")
        cls.user_three = User.objects.create(username="three")
        cls.speaker_one = cls.speaker_list.speaker_items.create(user=cls.user_one)
        cls.speaker_two = cls.speaker_list.speaker_items.create(user=cls.user_two)
        cls.speaker_three = cls.speaker_list.speaker_items.create(user=cls.user_three)

    def _mk_previous_spoken(self, user, count=1):
        # Don't forget that this will reorder lists on create!
        for i in range(count):
            self.speaker_list.speaker_items.create(user=user, started=now(), seconds=10)

    def test_simple_priority_for_less_spoken(self):
        self.assertEqual(
            [self.user_one.pk, self.user_two.pk, self.user_three.pk],
            self.speaker_list.reorder(),
        )

    def test_more_spoken_pushed_down(self):
        self._mk_previous_spoken(self.user_two)
        self.assertEqual(
            [self.user_one.pk, self.user_three.pk, self.user_two.pk],
            self.speaker_list.reorder(),
        )

    def test_safe_users_respected_initial_not_used(self):
        """
        User    Times spoken
        1       (0) ( removes themselves)
        2       (1)
        3       (0)
        """
        self._mk_previous_spoken(self.user_two)
        self.system.safe_positions = 1
        self.system.save()
        self.assertEqual(
            [self.user_one.pk, self.user_three.pk, self.user_two.pk],
            self.speaker_list.reorder(),
        )
        self.speaker_list.save()
        self.speaker_one.speaker_list.refresh_from_db()
        self.speaker_one.delete()
        self.assertEqual(
            [self.user_three.pk, self.user_two.pk],
            self.speaker_list.reorder(),
        )

    def test_safe_users_checked_with_current_order(self):
        self.speaker_list.speaker_items.all().delete()  # Start fresh here
        self.speaker_list.reorder()
        self.assertEqual([], self.speaker_list.order_list)
        self._mk_previous_spoken(self.user_two)
        self._mk_previous_spoken(self.user_one, count=2)
        self.system.safe_positions = 1
        self.system.save()
        speaker_one = self.speaker_list.speaker_items.create(
            user=self.user_one
        )  # Enters safe pos
        speaker_two = self.speaker_list.speaker_items.create(user=self.user_two)
        # Passes no 2
        speaker_three = self.speaker_list.speaker_items.create(user=self.user_three)
        self.assertEqual(
            [self.user_one.pk, self.user_three.pk, self.user_two.pk],
            self.speaker_list.reorder(),
        )

    def test_max_times_aborts_priority(self):
        self.system.settings = {"max_times": 1}
        self.system.save()
        # Both one and two will be treated as 1, so two won't have higher priority
        self.speaker_list.speaker_items.all().delete()  # Start fresh here
        self._mk_previous_spoken(self.user_one, 2)
        self._mk_previous_spoken(self.user_two, 1)
        speaker_one = self.speaker_list.speaker_items.create(user=self.user_one)
        speaker_two = self.speaker_list.speaker_items.create(user=self.user_two)
        speaker_three = self.speaker_list.speaker_items.create(user=self.user_three)
        self.assertEqual(
            [self.user_three.pk, self.user_one.pk, self.user_two.pk],
            self.speaker_list.reorder(),
        )
