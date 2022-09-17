from django.contrib.auth import get_user_model
from django.test import TestCase
from django_fsm import TransitionNotAllowed

from voteit.components.app.components.message import FlashMessage
from voteit.components.app.components.proposal_print import ProposalPrint
from voteit.meeting.models import Meeting

User = get_user_model()


class MeetingComponentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # cls.moderator = User.objects.get(username="moderator")
        cls.meeting = Meeting.objects.create()
        cls.message = cls.meeting.components.create(component_name=FlashMessage.name)
        cls.print = cls.meeting.components.create(component_name=ProposalPrint.name)

    def test_wf_constraint(self):
        self.print.enable()
        with self.assertRaises(TransitionNotAllowed):
            self.message.enable()
        self.message.settings = {"msg": "a"}
        self.message.enable()
        self.message.settings_data = {}
        self.message.disable()
        # Only checked on enable
        with self.assertRaises(TransitionNotAllowed):
            self.message.enable()

    def test_settings_no_schema(self):
        with self.assertRaises(ValueError):
            self.print.settings = {}
