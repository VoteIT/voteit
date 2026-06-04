from django.test import TestCase
from rest_framework.exceptions import ValidationError

from voteit.core.rest_api.utils import drf_do_transition
from voteit.core.rest_api.utils import get_valid_transitions
from voteit.core.rest_api.utils import get_valid_transitions_dict


class UtilsTests(TestCase):
    """
    These utilities are for django-fsm models only. Testing against Poll (still FSM).
    Meeting has been migrated to python-statemachine.
    """

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.organisation.models import Organisation
        from voteit.poll.models import Poll

        org = Organisation.objects.create()
        cls.meeting = Meeting.objects.create(organisation=org, state="upcoming")
        cls.ai = cls.meeting.agenda_items.create(state="upcoming")
        cls.poll = Poll.objects.create(
            method_name="simple", agenda_item=cls.ai, meeting=cls.meeting
        )

    def test_valid_states_poll_private(self):
        self.assertEqual(
            ["ongoing", "upcoming"],
            sorted(x.name for x in get_valid_transitions(self.poll)),
        )

    def test_drf_do_transition_poll(self):
        valid_transitions = get_valid_transitions_dict(self.poll)
        with self.assertRaises(ValidationError):
            drf_do_transition(
                instance=self.poll,
                valid_transitions=dict(valid_transitions),
                transition_name="ongoing",
                user=None,
            )
