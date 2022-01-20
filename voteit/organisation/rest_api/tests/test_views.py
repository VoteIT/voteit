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


@override_settings(ID_PROXY_API_KEY="secret")
class IDProxyOrganisationViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.organisation.models import Organisation

        cls.org = Organisation.objects.get(pk=1)

    def test_create(self):
        url = reverse("id-organisations-list")
        data = {
            "title": "Item no 2?",
        }
        response = self.client.post(url, data, HTTP_AUTHORIZATION=f"api-key secret")
        self.assertEqual(201, response.status_code)

    def test_get(self):
        url = reverse("id-organisations-detail", kwargs={"pk": self.org.pk})
        response = self.client.get(url, HTTP_AUTHORIZATION=f"api-key secret")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(self.org.pk, data["pk"])

    def test_list(self):
        url = reverse("id-organisations-list")
        response = self.client.get(url, HTTP_AUTHORIZATION=f"api-key secret")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(1, len(data))

    def test_bad_auth(self):
        url = reverse("id-organisations-list")
        response = self.client.get(url, HTTP_AUTHORIZATION=f"api-key not working")
        self.assertEqual(response.status_code, 401)

    def test_patch(self):
        url = reverse("id-organisations-detail", kwargs={"pk": self.org.pk})
        data = {
            "title": "Item no 1",
        }
        response = self.client.patch(url, data, HTTP_AUTHORIZATION=f"api-key secret")
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.org.refresh_from_db()
        self.assertEqual("Item no 1", self.org.title)
        self.assertEqual("Item no 1", data["title"])


@override_settings(ID_PROXY_API_KEY="secret")
class IDProxyProviderViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.organisation.models import OAuth2Provider

        cls.provider = OAuth2Provider.objects.get(pk=1)

    def test_create(self):
        url = reverse("id-providers-list")
        data = {
            "title": "Providerish",
            "client_id": "client_id",
            "client_secret": "sssshhhhh",
            "redirect_url": "http://localhost/hello",
            "auth_url": "http://localhost/hello",
            "token_url": "http://localhost/hello",
            "identity_url": "http://localhost/hello",
        }
        response = self.client.post(url, data, HTTP_AUTHORIZATION=f"api-key secret")
        self.assertEqual(201, response.status_code)

    def test_get(self):
        url = reverse("id-providers-detail", kwargs={"pk": self.provider.pk})
        response = self.client.get(url, HTTP_AUTHORIZATION=f"api-key secret")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(self.provider.pk, data["pk"])
        self.assertNotIn("client_id", data)
        self.assertNotIn("client_secret", data)

    def test_list(self):
        url = reverse("id-providers-list")
        response = self.client.get(url, HTTP_AUTHORIZATION=f"api-key secret")
        self.assertEqual(response.status_code, 200)
        list_data = response.json()
        self.assertEqual(1, len(list_data))
        data = list_data[0]
        self.assertNotIn("client_id", data)
        self.assertNotIn("client_secret", data)
        self.assertEqual(1, data["pk"])

    def test_patch(self):
        url = reverse("id-providers-detail", kwargs={"pk": self.provider.pk})
        data = {
            "title": "Item no 1",
        }
        response = self.client.patch(url, data, HTTP_AUTHORIZATION=f"api-key secret")
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.provider.refresh_from_db()
        self.assertEqual("Item no 1", self.provider.title)
        self.assertEqual("Item no 1", data["title"])

    def test_bad_auth(self):
        url = reverse("id-providers-list")
        response = self.client.get(url, HTTP_AUTHORIZATION=f"api-key not working")
        self.assertEqual(response.status_code, 401)
