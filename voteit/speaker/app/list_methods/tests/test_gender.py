from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.timezone import now

from voteit.messaging.testing import action_of

from voteit.components.models import MeetingComponent
from voteit.meeting.models import Meeting
from voteit.participant_tags.components import GenderTags
from voteit.speaker.app.list_methods.gender import GenderAndPriority
from voteit.speaker.app.list_methods.simple import Simple
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem

User = get_user_model()


class GenderAndPriorityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.PRIORITY_GENDERS = ["f", "nb"]
        cls.room = cls.meeting.rooms.create()
        cls.system: SpeakerListSystem = SpeakerListSystem.objects.create(
            method_name=GenderAndPriority.name,
            room=cls.room,
            settings_data={"priority_genders": cls.PRIORITY_GENDERS},
            safe_positions=0,
        )
        cls.speaker_list = SpeakerList.objects.create(speaker_system=cls.system)
        cls.pk_to_username = {}
        for username in ("one", "two", "three", "four", "five", "six", "seven"):
            user = User.objects.create(username=username)
            setattr(cls, f"user_{username}", user)
            cls.pk_to_username[user.pk] = username
        # And genders
        cls.tags_one = cls.meeting.participant_tags.create(
            user=cls.user_one, tags={GenderTags.namespace: "f"}
        )
        cls.tags_two = cls.meeting.participant_tags.create(
            user=cls.user_two, tags={GenderTags.namespace: "m"}
        )
        cls.tags_three = cls.meeting.participant_tags.create(
            user=cls.user_three, tags={GenderTags.namespace: "m"}
        )
        cls.tags_four = cls.meeting.participant_tags.create(
            user=cls.user_four, tags={GenderTags.namespace: "nb"}
        )
        cls.tags_five = cls.meeting.participant_tags.create(
            user=cls.user_five, tags={GenderTags.namespace: "m"}
        )
        cls.tags_six = cls.meeting.participant_tags.create(
            user=cls.user_six, tags={GenderTags.namespace: "bad-data"}
        )
        # seven missing on purpose
        # All in queue
        cls.speaker_one = cls.speaker_list.speaker_items.create(user=cls.user_one)
        cls.speaker_two = cls.speaker_list.speaker_items.create(user=cls.user_two)
        cls.speaker_three = cls.speaker_list.speaker_items.create(user=cls.user_three)
        cls.speaker_four = cls.speaker_list.speaker_items.create(user=cls.user_four)
        cls.speaker_five = cls.speaker_list.speaker_items.create(user=cls.user_five)
        cls.speaker_six = cls.speaker_list.speaker_items.create(user=cls.user_six)
        cls.speaker_seven = cls.speaker_list.speaker_items.create(user=cls.user_seven)
        # And add some irrelevant speakers
        cls.other_speaker_list = SpeakerList.objects.create(speaker_system=cls.system)
        for i, user in enumerate(
            [cls.user_six, cls.user_five, cls.user_four, cls.user_three, cls.user_two],
            start=1,
        ):
            for _ in range(i):
                cls.other_speaker_list.speaker_items.create(
                    user=user, started=now(), seconds=10
                )
        # Initial order
        cls.speaker_list.reorder()

    def _mk_previous_spoken(self, user, count=1):
        for i in range(count):
            self.speaker_list.speaker_items.create(user=user, started=now(), seconds=10)

    def _pks_to_usernames(self, *args):
        return [self.pk_to_username[x] for x in args]

    def test_queryset_annotations(self):
        self._mk_previous_spoken(
            self.user_one,
        )
        self.assertEqual(
            {
                (self.user_one.pk, 1, "f"),
                (self.user_two.pk, 0, "m"),
                (self.user_three.pk, 0, "m"),
                (self.user_four.pk, 0, "nb"),
                (self.user_five.pk, 0, "m"),
                (self.user_six.pk, 0, "bad-data"),
                (self.user_seven.pk, 0, None),
            },
            set(
                self.system.method.get_queryset(self.speaker_list).values_list(
                    "user_id", "spoken_count", "gender_tag"
                )
            ),
        )

    def test_all_same_base_prio(self):
        self.assertEqual(
            [
                "one",
                "two",
                "four",  # Passed
                "three",
                "five",
                "six",
                "seven",
            ],
            self._pks_to_usernames(*self.speaker_list.order_list),
        )

    def test_initial_speakers_with_history(self):
        self._mk_previous_spoken(self.user_one)
        self._mk_previous_spoken(self.user_four)
        self.speaker_list.reorder()
        self.assertEqual(
            [
                "two",
                "three",
                "five",
                "six",
                "seven",
                "one",  # Spoken before
                "four",  # Spoken before
            ],
            self._pks_to_usernames(*self.speaker_list.order_list),
        )

    def test_six_enters_with_priority(self):
        self.tags_six.tags = {GenderTags.namespace: "f"}
        self.tags_six.save()
        self.speaker_list.reorder()
        self.assertEqual(
            [
                "one",
                "two",
                "four",
                "three",
                "six",
                "five",
                "seven",
            ],
            self._pks_to_usernames(*self.speaker_list.order_list),
        )

    def test_changes_gender(self):
        self.assertEqual(
            [
                "one",
                "two",
                "four",
                "three",
                "five",
                "six",
                "seven",
            ],
            self._pks_to_usernames(*self.speaker_list.order_list),
        )
        self.tags_three.tags = {GenderTags.namespace: "f"}
        self.tags_three.save()
        self.speaker_list.reorder()
        # Initial ordering kept, three won't pass four
        self.assertEqual(
            [
                "one",
                "two",
                "four",
                "three",
                "five",
                "six",
                "seven",
            ],
            self._pks_to_usernames(*self.speaker_list.order_list),
        )
        # Seven gets a valid priority gender
        self.meeting.participant_tags.create(
            user=self.user_seven, tags={GenderTags.namespace: "f"}
        )
        self.speaker_list.reorder()
        self.assertEqual(
            [
                "one",
                "two",
                "four",
                "three",
                "five",
                "seven",
                "six",
            ],
            self._pks_to_usernames(*self.speaker_list.order_list),
        )

    def test_initial_safe_unprioritized(self):
        self.system.safe_positions = 3
        self.system.save()
        self.tags_one.delete()
        self.tags_two.delete()
        self.speaker_list.order = ""
        self.speaker_list.reorder()
        self.assertEqual(
            [
                "one",
                "two",
                "three",
                "four",  # Not moved
                "five",
                "six",
                "seven",
            ],
            self._pks_to_usernames(*self.speaker_list.order_list),
        )

    def test_more_spoken_pushed_down_regardless_of_priority(self):
        self._mk_previous_spoken(
            self.user_four,
        )
        self.speaker_list.reorder()
        self.assertEqual(
            [
                "one",
                "two",
                "three",
                "five",
                "six",
                "seven",
                "four",  # Pushed down
            ],
            self._pks_to_usernames(*self.speaker_list.order_list),
        )

    def test_speaker_speaking_and_reordering_with_safe_pos(self):
        """
        1 safe pos.
        User    Times spoken
        1       (1) Speaking right now
        2       (1) Safe pos
        3       (0)
        4       (0) Moved up to 3
        ...
        """
        self.system.safe_positions = 1
        self.system.save()
        self._mk_previous_spoken(self.user_one)
        self._mk_previous_spoken(self.user_two)
        self.speaker_one.started = now()
        self.speaker_one.save()
        self.speaker_list.reorder()
        self.assertEqual(
            [
                "one",
                "two",
                "four",  # Pushed up
                "three",
                "five",
                "six",
                "seven",
            ],
            self._pks_to_usernames(*self.speaker_list.order_list),
        )

    def test_speaker_speaking_and_reordering_with_safe_pos_and_safe_pos_prio(self):
        """
        1 safe pos.
        User    Times spoken
        1       (1) Speaking right now
        2       (1) Safe pos (f)
        3       (0)
        4       (0) Not moved (nb)
        ...
        """
        # self.skipTest("This doesn't work as expected")
        self.system.safe_positions = 1
        self.system.save()
        self._mk_previous_spoken(self.user_one)
        self._mk_previous_spoken(self.user_two)
        self.tags_two.tags = {GenderTags.namespace: "f"}
        self.tags_two.save()
        self.speaker_list.order = ""
        self.speaker_one.started = now()
        self.speaker_one.save()
        self.speaker_list.reorder()
        self.assertEqual(
            [
                "one",
                "two",
                "three",
                "four",  # Not moved due to the gender of 2
                "five",
                "six",
                "seven",
            ],
            self._pks_to_usernames(*self.speaker_list.order_list),
        )

    def test_automatic_settings_on_add(self):
        component = self.meeting.components.filter(
            component_name=action_of(GenderTags)
        ).first()
        self.assertIsInstance(component, MeetingComponent)
        self.assertEqual({"tags": ["m", "f", "nb"]}, component.settings_data)
        self.assertTrue(component.enabled)

    def test_automatic_disable_on_delete(self):
        self.system.delete()
        component = self.meeting.components.filter(
            component_name=action_of(GenderTags)
        ).first()
        self.assertIsInstance(component, MeetingComponent)
        self.assertFalse(component.enabled)

    def test_automatic_disable_on_change(self):
        self.system.method_name = Simple.name
        self.system.save()
        component = self.meeting.components.filter(
            component_name=action_of(GenderTags)
        ).first()
        self.assertIsInstance(component, MeetingComponent)
        self.assertFalse(component.enabled)

    def test_keep_component_when_multiple_lists_exist(self):
        room2 = self.meeting.rooms.create()
        self.meeting.speaker_systems.create(
            room=room2, method_name=GenderAndPriority.name
        )
        self.system.delete()
        component = self.meeting.components.filter(
            component_name=action_of(GenderTags)
        ).first()
        self.assertTrue(component.enabled)
