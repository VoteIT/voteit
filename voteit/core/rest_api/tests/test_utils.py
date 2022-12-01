from django.test import TestCase
from rest_framework.exceptions import ValidationError

from voteit.core.rest_api.utils import drf_do_transition
from voteit.core.rest_api.utils import get_valid_transitions
from voteit.core.rest_api.utils import get_valid_transitions_dict


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
            ["ongoing", "request_delete"],
            [x.name for x in get_valid_transitions(self.meeting)],
        )

    def test_valid_states_ongoing(self):
        self.meeting.ongoing()
        self.meeting.save()
        self.assertEqual(
            [
                "close",
                "request_delete",
                "upcoming",
            ],
            [x.name for x in get_valid_transitions(self.meeting)],
        )

    def test_drf_do_transition(self):
        user = self.meeting.participants.create()
        valid_transitions = get_valid_transitions_dict(self.meeting)
        self.meeting.er_policy_name = "jeff"
        with self.assertRaises(ValidationError) as cm:
            drf_do_transition(
                instance=self.meeting,
                valid_transitions=dict(valid_transitions),
                transition_name="ongoing",
                user=user,
            )
        self.assertIn(
            "Must have valid electoral register policy name", str(cm.exception)
        )
