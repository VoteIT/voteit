from django.urls import reverse
from rest_framework.test import APITestCase


class OrganisationViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.organisation.models import Organisation
        from voteit.organisation.roles import ROLE_ORG_MANAGER

        cls.org: Organisation = Organisation.objects.create(
            title="Test org",
        )
        cls.manager = cls.org.users.create(username="manager")
        cls.user = cls.org.users.create(username="user")
        cls.org.add_roles(cls.manager, ROLE_ORG_MANAGER)

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

    def test_get_anon(self):
        url = f"/api/organisations/{self.org.pk}/"
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

    def test_list_of_one(self):
        # Note: This is subject to change. For now you should get only one organisation.
        from voteit.organisation.models import Organisation

        other_org = Organisation.objects.create(title="Test org 2")
        url = "/api/organisations/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json()))
        # Even though not in list, you can still retrieve each organisation. Yes, this is kind of weird.
        for org in (self.org, other_org):
            response = self.client.get(f"/api/organisations/{org.pk}/")
            self.assertEqual(response.status_code, 200)
