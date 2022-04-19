from django.contrib.auth import get_user_model
from dolly.utils import get_data_id_struct

from voteit.core.utils import get_model_by_shortname
from voteit.meeting.models import Meeting
from voteit.organisation.models import Organisation

User = get_user_model()

from django.test import TestCase


class MeetingCloneTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture", "full_ai_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.organisation: Organisation = Organisation.objects.get(pk=1)

    def setUp(self):
        pass

    def test_collect_without_restrictions(self):
        from voteit.meeting.utils import collect_meeting

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
        from voteit.meeting.utils import collect_meeting
        from voteit.meeting.utils import get_default_models_ignored_on_clone

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
        from voteit.meeting.utils import clone_meeting
        from voteit.meeting.utils import collect_meeting
        from voteit.meeting.utils import get_default_models_ignored_on_clone

        counted = {}
        ignored_types = get_default_models_ignored_on_clone()
        data = collect_meeting(self.meeting, exclude=ignored_types)
        for m, values in data.items():
            counted[m] = m.objects.all().count()
        initial_pk = self.meeting.pk
        new_meeting = clone_meeting(self.meeting)
        self.assertNotEqual(new_meeting.pk, initial_pk)
        for m, initial_count in counted.items():
            self.assertEqual(initial_count * 2, m.objects.all().count())
