from django.test import TestCase


class OrganisationTests(TestCase):
    @property
    def Organisation(self):
        from voteit.organisation.models import Organisation

        return Organisation

    @property
    def Meeting(self):
        from voteit.meeting.models import Meeting

        return Meeting

    def test_meeting_relation(self):
        org = self.Organisation.objects.create()
        meeting = self.Meeting.objects.create(organisation=org)
        self.assertEqual(org, meeting.organisation)
