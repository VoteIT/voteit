from django.test import TestCase

from voteit.core.rest_api.utils import get_valid_transitions


class UtilsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.organisation.models import Organisation

        org = Organisation.objects.create()
        cls.meeting = Meeting.objects.create(
            er_policy_name="auto_before_poll", organisation=org, state="upcoming"
        )

    def setUp(self):
        self.meeting.refresh_from_db()

    def test_valid_states_upcoming(self):
        self.assertEqual(
            ["ongoing"], [x.name for x in get_valid_transitions(self.meeting)]
        )

    def test_valid_states_ongoing(self):
        self.meeting.ongoing()
        self.meeting.save()
        self.assertEqual(
            [
                "close",
                "upcoming",
            ],
            [x.name for x in get_valid_transitions(self.meeting)],
        )
