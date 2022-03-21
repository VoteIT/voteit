from http import HTTPStatus

from django.urls import reverse
from rest_framework.test import APITestCase


class OrganisationRolesTests(APITestCase):
    list_url = reverse("organisationroles-list")

    @classmethod
    def setUpTestData(cls):
        from ..models import Organisation

        cls.organisation = org = Organisation.objects.create(title="Test me")
        cls.manager = org.users.create(username="manager")
        org.add_roles(cls.manager, "org_manager")
        cls.member = org.users.create(username="member")

    def test_unauthorized(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, HTTPStatus.UNAUTHORIZED)

    def test_manager(self):
        self.client.force_login(self.manager)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(
            len(response.json()),
            1,
            "Managers should be able to list organisation roles",
        )

    def test_member(self):
        self.client.force_login(self.member)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(
            len(response.json()),
            0,
            "Only managers should be able to list organisation roles",
        )

    def test_other_org(self):
        from ..models import Organisation

        org = Organisation.objects.create(title="Other org")
        user = org.users.create(username="omanager")
        org.add_roles(user, "org_manager")
        self.client.force_login(self.manager)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(
            len(response.json()),
            1,
            "Only organisation roles in users organisation should be listed",
        )
        self.assertEqual(
            response.json()[0]["user"]["pk"],
            self.manager.pk,
        )
