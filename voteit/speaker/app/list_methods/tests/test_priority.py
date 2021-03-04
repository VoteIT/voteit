from django.contrib.auth.models import User
from django.test import TestCase


class PriorityTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        self.system = SpeakerListSystem.objects.create(method_name="priority")
        self.speaker_list = SpeakerList.objects.create(speaker_system=self.system)
        self.user_one = User.objects.create(username="one")
        self.user_two = User.objects.create(username="two")
        self.user_three = User.objects.create(username="three")
        self.speaker_one = self.speaker_list.speaker_items.create(user=self.user_one)
        self.speaker_two = self.speaker_list.speaker_items.create(user=self.user_two)
        self.speaker_three = self.speaker_list.speaker_items.create(
            user=self.user_three
        )

    def _mk_previous_spoken(self, user, count=1):
        # Don't forget that this will reorder lists on create!
        for i in range(count):
            old_entry = self.speaker_list.speaker_items.create(user=user)
            old_entry.order = None
            old_entry.save()

    def test_simple_priority_for_less_spoken(self):
        self.assertEqual(
            [self.speaker_one.pk, self.speaker_two.pk, self.speaker_three.pk],
            self.speaker_list.reorder(),
        )

    def test_more_spoken_pushed_down(self):
        self._mk_previous_spoken(self.user_two)
        self.assertEqual(
            [self.speaker_one.pk, self.speaker_three.pk, self.speaker_two.pk],
            self.speaker_list.reorder(),
        )

    def test_safe_users_respected(self):
        self._mk_previous_spoken(self.user_two)
        self._mk_previous_spoken(self.user_three, count=2)
        self.assertEqual(
            [self.speaker_one.pk, self.speaker_two.pk, self.speaker_three.pk],
            self.speaker_list.reorder(),
        )
        # 2 made safe
        self.speaker_two.safe_pos = True
        self.speaker_two.save()
        self.assertEqual(
            [self.speaker_two.pk, self.speaker_one.pk, self.speaker_three.pk],
            self.speaker_list.reorder(),
        )

    def test_max_times_aborts_priority(self):
        self.system.settings = {"max_times": 1}
        # Both one and two will be treated as 1, so two won't have higher priority
        self._mk_previous_spoken(self.user_one, 3)
        self._mk_previous_spoken(self.user_two, 2)
        self.assertEqual(
            [self.speaker_three.pk, self.speaker_one.pk, self.speaker_two.pk],
            self.speaker_list.reorder(),
        )
