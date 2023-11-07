from http import HTTPStatus

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from voteit.bug_reports.models import BugReport
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.organisation.models import Organisation

User = get_user_model()


class BugReportRestTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(title="Testing org")
        cls.meeting = Meeting.objects.create(title="Test meeting", organisation=cls.org)
        cls.user = User.objects.create_user("testing", organisation=cls.org)
        cls.meeting.add_roles(cls.user, ROLE_PARTICIPANT)
        cls.url = reverse("bugreport-list")

    @property
    def example_report(self):
        return {
            "description": "error description",
            "user_platform": {},
            "meeting": self.meeting.pk,
        }

    def test_unauthenticated(self):
        response = self.client.post(self.url, self.example_report)
        self.assertEqual(
            response.status_code,
            HTTPStatus.UNAUTHORIZED,
            "Unauthenticated users should not be able to list bug reports",
        )

    def _create(self, user, report_data):
        self.client.force_login(user)
        return self.client.post(self.url, report_data)

    def test_create(self):
        response = self._create(self.user, self.example_report)
        self.assertEqual(
            response.status_code, HTTPStatus.CREATED, "Bug report creation failed"
        )
        self.assertEqual(BugReport.objects.count(), 1, "Bug report count wrong")

    def test_list(self):
        other_user = User.objects.create_user("other", organisation=self.org)
        self.meeting.add_roles(other_user, ROLE_PARTICIPANT)
        self._create(other_user, self.example_report)
        self._create(self.user, self.example_report)
        response = self.client.get(self.url)
        self.assertEqual(
            response.status_code, HTTPStatus.OK, "Authenticated listing should be ok"
        )
        self.assertEqual(len(response.data), 1, "Incorrect report list length")
        self.assertEqual(response.data[0]["user"], self.user.pk, "Incorrect user")
