from django.urls import reverse
from rest_framework.test import APITestCase


class OrganisationViewSetTests(APITestCase):
    def setUp(self):
        from voteit.organisation.models import Organisation
        from voteit.organisation.roles import ROLE_ORG_MANAGER

        self.org: Organisation = Organisation.objects.create(
            title="Test org",
        )
        self.manager = self.org.users.create(username="manager")
        self.user = self.org.users.create(username="user")
        self.org.add_roles(self.manager, ROLE_ORG_MANAGER)

    def test_create(self):
        url = f"/api/organisations/"
        data = {
            "title": "Item no 1",
        }
        for user, status in (
            (None, 401),
            (self.user, 405),
            (self.manager, 405),
        ):
            if user:
                self.client.force_login(user)
            response = self.client.post(url, data)
            self.assertEqual(
                response.status_code,
                status,
                f"{user} action returned wrong response code",
            )

    def test_get(self):
        url = f"/api/organisations/{self.org.pk}/"
        self.client.force_login(self.manager)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(self.org.pk, data["pk"])

    def test_patch_manager(self):
        url = f"/api/organisations/{self.org.pk}/"
        self.client.force_login(self.manager)
        response = self.client.patch(url, {"title": "Hello"})
        self.assertEqual(response.status_code, 200)

    def test_patch_user(self):
        url = f"/api/organisations/{self.org.pk}/"
        self.client.force_login(self.user)
        response = self.client.patch(url, {"title": "Hello"})
        self.assertEqual(response.status_code, 403)

    def test_list(self):
        url = f"/api/organisations/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(1, len(data))
