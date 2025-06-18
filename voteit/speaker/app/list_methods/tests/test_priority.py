import random

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.timezone import now

from voteit.core.testing import SetSeed
from voteit.meeting.models import Meeting
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem

User = get_user_model()


class PriorityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.room = cls.meeting.rooms.create()
        cls.system = SpeakerListSystem.objects.create(
            method_name="priority", room=cls.room
        )
        cls.speaker_list = SpeakerList.objects.create(speaker_system=cls.system)
        cls.user_one = User.objects.create(username="one")
        cls.user_two = User.objects.create(username="two")
        cls.user_three = User.objects.create(username="three")
        cls.user_four = User.objects.create(username="four")
        cls.user_five = User.objects.create(username="five")
        cls.user_six = User.objects.create(username="six")
        cls.speaker_one = cls.speaker_list.speaker_items.create(user=cls.user_one)
        cls.speaker_two = cls.speaker_list.speaker_items.create(user=cls.user_two)
        cls.speaker_three = cls.speaker_list.speaker_items.create(user=cls.user_three)
        cls.speaker_list.reorder()

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
        # self.assertEqual([], self.speaker_list.order_list)
        self._mk_previous_spoken(self.user_two)
        self._mk_previous_spoken(self.user_one, count=2)
        self.system.safe_positions = 1
        self.system.save()
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

    def test_multiple_speakers(self):
        self.system.safe_positions = 1
        self.system.settings = {"max_times": 4}
        self.system.save()
        self._mk_previous_spoken(self.user_two, 1)
        self._mk_previous_spoken(self.user_three, 2)
        self.speaker_list.reorder()
        self.assertEqual(
            [self.user_one.pk, self.user_two.pk, self.user_three.pk],
            self.speaker_list.order_list,
        )
        speaker_four = self.speaker_list.speaker_items.create(user=self.user_four)
        self.speaker_list.reorder()
        self.assertEqual(
            [self.user_one.pk, self.user_four.pk, self.user_two.pk, self.user_three.pk],
            self.speaker_list.order_list,
        )
        speaker_five = self.speaker_list.speaker_items.create(user=self.user_five)
        self._mk_previous_spoken(self.user_five, 1)
        self.speaker_list.reorder()
        self.assertEqual(
            [
                self.user_one.pk,
                self.user_four.pk,
                self.user_two.pk,
                self.user_five.pk,
                self.user_three.pk,
            ],
            self.speaker_list.order_list,
        )

    def test_multiple_speakers_no_max(self):
        self.system.safe_positions = 1
        self.system.settings = {"max_times": 0}
        self.system.save()
        self._mk_previous_spoken(self.user_two, 1)
        self._mk_previous_spoken(self.user_three, 2)
        self.speaker_list.reorder()
        self.assertEqual(
            [self.user_one.pk, self.user_two.pk, self.user_three.pk],
            self.speaker_list.order_list,
        )
        speaker_four = self.speaker_list.speaker_items.create(user=self.user_four)
        self.speaker_list.reorder()
        self.assertEqual(
            [self.user_one.pk, self.user_four.pk, self.user_two.pk, self.user_three.pk],
            self.speaker_list.order_list,
        )
        speaker_five = self.speaker_list.speaker_items.create(user=self.user_five)
        self._mk_previous_spoken(self.user_five, 1)
        self.speaker_list.reorder()
        self.assertEqual(
            [
                self.user_one.pk,
                self.user_four.pk,
                self.user_two.pk,
                self.user_five.pk,
                self.user_three.pk,
            ],
            self.speaker_list.order_list,
        )
        speaker_six = self.speaker_list.speaker_items.create(user=self.user_six)
        self._mk_previous_spoken(self.user_six, 2)
        self.speaker_list.reorder()
        self.assertEqual(
            [
                self.user_one.pk,
                self.user_four.pk,
                self.user_two.pk,
                self.user_five.pk,
                self.user_three.pk,
                self.user_six.pk,
            ],
            self.speaker_list.order_list,
        )

    def test_speaker_speaking_and_reordering_with_safe_pos(self):
        """
        1 safe pos.
        User    Times spoken
        1       (1) Speaking right now
        2       (1) Safe pos
        3       (0)
        4       (0) Will enter and reorder
        """
        self.system.safe_positions = 1
        self.system.save()
        self._mk_previous_spoken(self.user_one)
        self._mk_previous_spoken(self.user_two)
        self.speaker_one.started = now()
        self.speaker_one.save()
        self.speaker_four = self.speaker_list.speaker_items.create(user=self.user_four)
        self.assertEqual(
            [self.user_one.pk, self.user_two.pk, self.user_three.pk, self.user_four.pk],
            self.speaker_list.reorder(),
        )

    def test_speaker_further_down_and_reordering_with_safe_pos(self):
        """
        1 safe pos.
        User    Times spoken
        1       (1) Safe
        2       (0)
        3       (1) Speaking right now
        4       (0) Will enter and reorder
        """
        self.system.safe_positions = 1
        self._mk_previous_spoken(self.user_one)
        self._mk_previous_spoken(self.user_three)
        self.speaker_three.started = now()
        self.speaker_three.save()
        self.speaker_four = self.speaker_list.speaker_items.create(user=self.user_four)
        self.assertEqual(
            [self.user_one.pk, self.user_two.pk, self.user_four.pk, self.user_three.pk],
            self.speaker_list.reorder(),
        )

    def test_shuffle(self):
        """
        1 safe pos.
        User    Times spoken
        1       (1)
        2       (0)
        3       (1)
        4       (0)
        """
        self.system.safe_positions = 0
        self.system.save()
        self._mk_previous_spoken(self.user_one)
        self._mk_previous_spoken(self.user_three)
        self.speaker_four = self.speaker_list.speaker_items.create(user=self.user_four)
        random.seed(1337)
        self.speaker_list.shuffle()
        self.assertEqual(
            [self.user_two.pk, self.user_four.pk, self.user_three.pk, self.user_one.pk],
            self.speaker_list.order_list,
        )
        random.seed(1)
        self.speaker_list.shuffle()
        self.assertEqual(
            [self.user_four.pk, self.user_two.pk, self.user_three.pk, self.user_one.pk],
            self.speaker_list.order_list,
        )
        random.seed()

    def test_shuffle_safe_pos(self):
        """
        1 safe pos.
        User    Times spoken
        1       (0) Safe - nope
        2       (0) Safe - nope
        3       (0)
        4       (0)
        """
        self.system.safe_positions = 2
        self.system.save()
        self.speaker_four = self.speaker_list.speaker_items.create(user=self.user_four)
        random.seed(1337)
        self.speaker_list.shuffle()
        self.assertEqual(
            [self.user_three.pk, self.user_two.pk, self.user_one.pk, self.user_four.pk],
            self.speaker_list.order_list,
        )
        random.seed()
