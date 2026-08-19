from django.test import TestCase


from voteit.components.app.components.message import FlashMessage
from voteit.components.app.components.proposal_print import ProposalPrint
from voteit.meeting.models import Meeting


class MeetingComponentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.message = cls.meeting.components.create(component_name=FlashMessage.name)
        cls.print = cls.meeting.components.create(component_name=ProposalPrint.name)

    def test_enable_validates_settings(self):
        self.print.enable()
        self.assertTrue(self.print.enabled)
        with self.assertRaises(ValueError):
            self.message.enable()
        self.message.settings = {"msg": "a"}
        self.message.enable()
        self.assertTrue(self.message.enabled)
        self.message.settings_data = {}
        self.message.disable()
        self.assertFalse(self.message.enabled)
        # Only checked on enable
        with self.assertRaises(ValueError):
            self.message.enable()

    def test_settings_no_schema(self):
        with self.assertRaises(ValueError):
            self.print.settings = {}
