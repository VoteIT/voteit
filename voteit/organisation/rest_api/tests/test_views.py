from django.urls import reverse
from rest_framework.test import APITestCase
from django.test import override_settings


class OrganisationViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.organisation.models import Organisation
        from voteit.organisation.roles import ROLE_ORG_MANAGER

        # Note on these tests: The host for test client is always 'testserver'
        cls.org: Organisation = Organisation.objects.create(
            title="Test org", subdomain="testserver"
        )
        cls.manager = cls.org.users.create(username="manager")
        cls.user = cls.org.users.create(username="user")
        cls.org.add_roles(cls.manager, ROLE_ORG_MANAGER)
        cls.other_org: Organisation = Organisation.objects.create(
            title="Other org", subdomain="other"
        )
        cls.other_org_user = cls.other_org.users.create(username="other_org_user")

    def test_create(self):
        url = reverse("organisations-list")
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
        url = reverse("organisations-detail", kwargs={"pk": self.org.pk})
        self.client.force_login(self.manager)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(self.org.pk, data["pk"])

    def test_get_other(self):
        url = reverse("organisations-detail", kwargs={"pk": self.other_org})
        self.client.force_login(self.manager)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_get_anon_matching_domain(self):
        url = reverse("organisations-detail", kwargs={"pk": self.org.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_get_anon_other(self):
        url = reverse("organisations-detail", kwargs={"pk": self.other_org.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_patch_manager(self):
        url = reverse("organisations-detail", kwargs={"pk": self.org.pk})
        self.client.force_login(self.manager)
        response = self.client.patch(url, {"title": "Hello"})
        self.assertEqual(response.status_code, 200)

    def test_patch_manager_other(self):
        url = reverse("organisations-detail", kwargs={"pk": self.other_org.pk})
        self.client.force_login(self.manager)
        response = self.client.patch(url, {"title": "Hello"})
        self.assertEqual(response.status_code, 404)

    def test_patch_user(self):
        url = reverse("organisations-detail", kwargs={"pk": self.org.pk})
        self.client.force_login(self.user)
        response = self.client.patch(url, {"title": "Hello"})
        self.assertEqual(response.status_code, 403)

    def test_patch_user_other(self):
        url = reverse("organisations-detail", kwargs={"pk": self.other_org.pk})
        self.client.force_login(self.user)
        response = self.client.patch(url, {"title": "Hello"})
        self.assertEqual(response.status_code, 404)

    def test_list_anon(self):
        url = reverse("organisations-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(1, len(data))

    def test_list(self):
        self.client.force_login(self.user)
        url = reverse("organisations-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(1, len(data))

    def test_list_wrong_domain(self):
        self.client.force_login(self.other_org_user)
        url = reverse("organisations-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertEqual("You're logged in to another organisation", data["detail"])

    def test_list_subdomain_match(self):
        self.client.force_login(self.other_org_user)
        url = reverse("organisations-list")
        response = self.client.get(url, SERVER_NAME="other.voteit.se")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(1, len(data))

    @override_settings(USE_X_FORWARDED_HOST=True)
    def test_list_subdomain_proxy(self):
        self.client.force_login(self.other_org_user)
        url = reverse("organisations-list")
        response = self.client.get(url, HTTP_X_FORWARDED_HOST="other.voteit.se")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(1, len(data))

    def test_list_subdomain_regular_host(self):
        self.client.force_login(self.other_org_user)
        url = reverse("organisations-list")
        response = self.client.get(url, HTTP_HOST="other.voteit.se")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(1, len(data))
