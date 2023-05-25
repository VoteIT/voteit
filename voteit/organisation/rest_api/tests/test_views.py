from __future__ import annotations
from http import HTTPStatus
from typing import TYPE_CHECKING

from django.test import override_settings
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.timezone import now
from rest_framework.test import APITestCase

from voteit.core.loggers import notification_logger
from voteit.organisation.models import Organisation
from voteit.organisation.roles import ROLE_ORG_MANAGER

if TYPE_CHECKING:
    from voteit.core.models import User as UserType


class OrganisationViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.organisation.models import Organisation
        from voteit.organisation.roles import ROLE_ORG_MANAGER

        # Note on these tests: The host for test client is always 'testserver'
        cls.org: Organisation = Organisation.objects.create(
            title="Test org", host="testserver"
        )
        cls.manager = cls.org.users.create(username="manager")
        cls.user = cls.org.users.create(username="user")
        cls.org.add_roles(cls.manager, ROLE_ORG_MANAGER)
        cls.other_org: Organisation = Organisation.objects.create(
            title="Other org", host="other.voteit.se"
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

    def test_list_host_match(self):
        self.client.force_login(self.other_org_user)
        url = reverse("organisations-list")
        response = self.client.get(url, SERVER_NAME="other.voteit.se")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(1, len(data))

    @override_settings(USE_X_FORWARDED_HOST=True)
    def test_list_host_proxy(self):
        self.client.force_login(self.other_org_user)
        url = reverse("organisations-list")
        response = self.client.get(url, HTTP_X_FORWARDED_HOST="other.voteit.se")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(1, len(data))

    def test_list_host_regular_host(self):
        self.client.force_login(self.other_org_user)
        url = reverse("organisations-list")
        response = self.client.get(url, HTTP_HOST="other.voteit.se")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(1, len(data))


# @override_settings(ID_PROXY_API_KEY="secret")
# class IDProxyOrganisationViewSetTests(APITestCase):
#     fixtures = ["meeting_test_fixture"]
#
#     @classmethod
#     def setUpTestData(cls):
#         from voteit.organisation.models import Organisation
#
#         cls.org = Organisation.objects.get(pk=1)
#
#     def test_create(self):
#         url = reverse("id-organisations-list")
#         data = {
#             "title": "Item no 2?",
#             "provider": {
#                 "title": "Hello",
#                 "client_id": "client",
#                 "client_secret": "don't tell",
#             },
#         }
#         response = self.client.post(url, data, HTTP_API_KEY="secret")
#         self.assertEqual(201, response.status_code)
#
#     def test_get(self):
#         url = reverse("id-organisations-detail", kwargs={"pk": self.org.pk})
#         response = self.client.get(url, HTTP_API_KEY="secret")
#         self.assertEqual(response.status_code, 200)
#         data = response.json()
#         self.assertEqual(self.org.pk, data["pk"])
#
#     def test_list(self):
#         url = reverse("id-organisations-list")
#         response = self.client.get(url, HTTP_API_KEY=f"secret")
#         self.assertEqual(response.status_code, 200)
#         data = response.json()
#         self.assertEqual(1, len(data))
#
#     def test_bad_auth(self):
#         url = reverse("id-organisations-list")
#         response = self.client.get(url, HTTP_API_KEY=f"not working")
#         self.assertEqual(response.status_code, 401)
#
#     def test_patch(self):
#         url = reverse("id-organisations-detail", kwargs={"pk": self.org.pk})
#         data = {
#             "title": "Item no 1",
#             "provider": {
#                 "scope": "hello",
#             },
#         }
#         response = self.client.patch(url, data, HTTP_API_KEY="secret")
#         self.assertEqual(200, response.status_code)
#         data = response.json()
#         self.org.refresh_from_db()
#         self.org.provider.refresh_from_db()
#         self.assertEqual("Item no 1", self.org.title)
#         self.assertEqual("Item no 1", data["title"])
#         self.assertEqual("hello", self.org.provider.scope)
#         self.assertEqual("hello", data["provider"]["scope"])


class OrganisationRolesTests(APITestCase):
    list_url = reverse("organisationroles-list")

    @classmethod
    def setUpTestData(cls):
        from voteit.organisation.models import Organisation

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
        from voteit.organisation.models import Organisation

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


@override_settings(ID_PROXY_API_KEY="xxx")
class MatchOrphansViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organisation = org = Organisation.objects.create(
            title="Test me", host="betahaus.voteit.se"
        )
        cls.orphan = org.users.create(username="orphan", email="orphan@voteit.se")
        cls.orphan2 = org.users.create(username="orphan2", email="oliver@voteit.se")
        cls.claimed = org.users.create(
            username="claimed", email="claimed@voteit.se", identity_id="abc"
        )

    def _mk_auth(self):
        return {"HTTP_API_KEY": "xxx"}

    def test_no_payload(self):
        url = reverse("match-orphans-list")
        response = self.client.get(url, **self._mk_auth())
        self.assertEqual(400, response.status_code)
        self.assertIn("email_in", response.json())
        response = self.client.get(url, data={"email_in": ""}, **self._mk_auth())
        self.assertEqual(400, response.status_code)

    def test_no_api_key(self):
        url = reverse("match-orphans-list")
        response = self.client.get(url, data={"email_in": "jeff@blaha.se"})
        self.assertEqual(401, response.status_code)

    def test_several_matches(self):
        url = reverse("match-orphans-list")
        response = self.client.get(
            url,
            **self._mk_auth(),
            data={
                "email_in": "oliver@voteit.se,orphan@voteit.se,claimed@voteit.se",
            },
        )
        data = response.json()
        self.assertEqual(
            {"orphan@voteit.se", "oliver@voteit.se"},
            {x["email"] for x in data},
        )


@override_settings(ID_PROXY_API_KEY="xxx")
class HandleIdentitiesViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.beta_organisation: Organisation = Organisation.objects.create(
            title="Test me"
        )
        cls.beta_one: UserType = cls.beta_organisation.users.create(
            username="one", identity_id="one", last_login=now()
        )
        cls.beta_two: UserType = cls.beta_organisation.users.create(
            username="two", identity_id="two", last_login=now()
        )
        cls.other_org: Organisation = Organisation.objects.create(
            title="Other",
        )
        cls.other_three: UserType = cls.other_org.users.create(
            username="other", identity_id="other", last_login=now()
        )

    def _mk_auth(self):
        return {"HTTP_API_KEY": "xxx"}

    def _mk_query_url(self, query: dict):
        return f"{reverse('handle-identities-query')}?{urlencode(query)}"

    def _mk_merge_url(self, query: dict):
        return f"{reverse('handle-identities-merge')}?{urlencode(query)}"

    def test_no_auth(self):
        response = self.client.get(self._mk_query_url({"identity_in": "one,two"}))
        self.assertEqual(401, response.status_code)

    def test_basic_query(self):
        response = self.client.get(
            self._mk_query_url({"identity_in": "one,two"}),
            **self._mk_auth(),
        )
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(2, len(data))
        self.assertEqual({"one", "two"}, {x["identity_id"] for x in data})

    def test_no_payload(self):
        response = self.client.get(
            self._mk_query_url({"identity_in": ""}),
            **self._mk_auth(),
        )
        self.assertContains(response, "required", status_code=400)
