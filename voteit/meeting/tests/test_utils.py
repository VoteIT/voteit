from django.contrib.auth import get_user_model
from django.test import TestCase
from dolly.utils import get_data_id_struct

from voteit.core.utils import get_model_by_shortname
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.utils import clone_meeting
from voteit.meeting.utils import collect_meeting
from voteit.meeting.utils import get_default_models_ignored_on_clone
from voteit.organisation.models import Organisation
from voteit.participant_number.models import PNSystem
from voteit.participant_number.models import ParticipantNumber
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem

User = get_user_model()


class MeetingCloneTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture", "full_ai_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.organisation: Organisation = Organisation.objects.get(pk=1)
        cls.user = User.objects.get(pk=1)

    def test_collect_without_restrictions(self):
        data = collect_meeting(self.meeting)
        items = get_data_id_struct(data)
        self.assertEqual({1}, items.pop(get_model_by_shortname("organisation")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("organisation_roles")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("oauth2_provider")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("meeting")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("meeting_group")))
        self.assertEqual({1, 2, 3}, items.pop(get_model_by_shortname("agenda_item")))
        self.assertEqual({1, 2}, items.pop(get_model_by_shortname("discussion_post")))
        self.assertEqual({1, 2, 3}, items.pop(get_model_by_shortname("proposal")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("electoral_register")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("text_document")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("text_paragraph")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("diff_proposal")))
        self.assertEqual({1}, items.pop(get_model_by_shortname("poll")))
        self.assertEqual({1, 2}, items.pop(get_model_by_shortname("voter_weight")))
        self.assertEqual({1, 2}, items.pop(get_model_by_shortname("meeting_roles")))
        self.assertEqual({1, 2}, items.pop(get_model_by_shortname("vote")))
        self.assertEqual({1, 2, 3}, items.pop(get_model_by_shortname("user")))
        self.assertFalse(items)

    def test_collect_with_default_ignored(self):
        ignored_types = get_default_models_ignored_on_clone()
        data = collect_meeting(self.meeting, exclude=ignored_types)
        for m in ignored_types:
            self.assertNotIn(m, data)
        expected_names = {
            "meeting",
            "meeting_group",
            "agenda_item",
            "discussion_post",
            "proposal",
            "text_document",
            "diff_proposal",
        }
        for name in expected_names:
            m = get_model_by_shortname(name)
            self.assertIsNotNone(m)
            self.assertIsNotNone(data.pop(m))

    def test_clone_meeting(self):
        counted = {}
        ignored_types = get_default_models_ignored_on_clone()
        data = collect_meeting(self.meeting, exclude=ignored_types)
        for m, values in data.items():
            counted[m] = m.objects.all().count()
        initial_pk = self.meeting.pk
        new_meeting = clone_meeting(self.meeting, user=self.user)
        self.assertNotEqual(new_meeting.pk, initial_pk)
        for m, initial_count in counted.items():
            self.assertEqual(initial_count * 2, m.objects.all().count())
        self.assertEqual("Copy of Testfixture meeting", new_meeting.title)
        self.assertEqual(
            {ROLE_MODERATOR, ROLE_PARTICIPANT}, new_meeting.get_roles(self.user)
        )

    def test_clone_with_active_speakerlist(self):
        room = self.meeting.rooms.create()
        sls: SpeakerListSystem = self.meeting.speaker_systems.create(
            method_name="simple", room=room
        )
        slist = sls.speaker_lists.create()
        sls.active_list = slist
        sls.save()
        self.assertEqual(1, SpeakerListSystem.objects.count())
        self.assertEqual(1, SpeakerList.objects.count())
        new_meeting = clone_meeting(self.meeting, user=self.user)
        self.assertEqual(2, SpeakerListSystem.objects.count())
        self.assertEqual(1, new_meeting.speaker_systems.count())
        self.assertEqual(1, SpeakerList.objects.count())

    def test_reset_wf(self):
        self.meeting.state = "ongoing"
        self.meeting.save()
        self.assertEqual(1, self.meeting.agenda_items.filter(state="private").count())
        self.assertEqual(2, self.meeting.agenda_items.filter(state="upcoming").count())
        new_meeting = clone_meeting(self.meeting, user=self.user, reset_wf=True)
        self.assertEqual("upcoming", new_meeting.state)
        self.assertEqual(3, new_meeting.agenda_items.filter(state="private").count())
        self.assertEqual(0, new_meeting.agenda_items.filter(state="ongoing").count())

    def test_related_to_ignored(self):
        pns: PNSystem = PNSystem.objects.create(meeting=self.meeting)
        number = pns.numbers.create(user=self.user, number=1)
        self.assertEqual(1, ParticipantNumber.objects.count())
        new_meeting = clone_meeting(self.meeting, user=self.user)
        new_meeting.refresh_from_db()
        with self.assertRaises(PNSystem.DoesNotExist):
            new_meeting.pn_system
        self.assertEqual(1, ParticipantNumber.objects.count())
