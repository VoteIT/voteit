from __future__ import annotations
from http import HTTPStatus
from typing import TYPE_CHECKING

from django.test import override_settings
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.timezone import now
from rest_framework.test import APITestCase

from voteit.core.testing import run_permission_tests
from voteit.organisation.models import Organisation
from voteit.organisation.roles import ROLE_MEETING_CREATOR
from voteit.organisation.roles import ROLE_ORG_MANAGER

if TYPE_CHECKING:
    from voteit.core.models import User as UserType


@override_settings(ID_HOST="https://testserver")
class OrganisationViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
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
        cls.other_org_manager = cls.other_org.users.create(username="other_org_manager")
        cls.other_org.add_roles(cls.other_org_manager, ROLE_ORG_MANAGER)
        cls.other_org_response = {
            "active": True,
            "body": "",
            "components": [],
            "help_info": "",
            "id_host": "https://testserver",
            "login_url": None,
            "page_title": "Other org",
            "scope": [],
            "title": "Other org",
            "pk": cls.other_org.pk,
        }

    def test_create(self):
        url = reverse("organisation-list")
        data = {
            "title": "Item no 1",
        }
        for func, params in run_permission_tests(
            self,
            url=url,
            data=data,
            method="POST",
            expected=(
                (self.manager, 405),
                (None, 401),
            ),
        ):
            func(*params)

    def test_list(self):
        url = reverse("organisation-list")
        expected_data = {
            "active": True,
            "body": "",
            "components": [],
            "help_info": "",
            "id_host": "https://testserver",
            "login_url": None,
            "page_title": "Test org",
            "pk": self.org.pk,
            "scope": [],
            "title": "Test org",
        }
        for func, params in run_permission_tests(
            self,
            url=url,
            expected=(
                (self.manager, 200, expected_data),
                (self.user, 200, expected_data),
                (None, 200, expected_data),
                (
                    self.other_org_user,
                    401,
                    {"detail": "You're logged in to another organisation"},
                ),
                (
                    self.other_org_manager,
                    401,
                    {"detail": "You're logged in to another organisation"},
                ),
            ),
        ):
            func(*params)

    def test_patch(self):
        url = reverse("organisation-change")
        data = {"body": "Hello"}
        for func, params in run_permission_tests(
            self,
            url=url,
            data=data,
            method="PATCH",
            expected=(
                (self.manager, 200, data),
                (self.user, 403),
                (None, 401),
            ),
        ):
            func(*params)

    def test_list_host_match(self):
        self.client.force_login(self.other_org_user)
        url = reverse("organisation-list")
        response = self.client.get(url, SERVER_NAME="other.voteit.se")
        data = response.json()
        self.assertEqual(response.status_code, 200, data)
        self.assertDictEqual(self.other_org_response, data)

    @override_settings(USE_X_FORWARDED_HOST=True)
    def test_list_host_proxy(self):
        self.client.force_login(self.other_org_user)
        url = reverse("organisation-list")
        response = self.client.get(url, HTTP_X_FORWARDED_HOST="other.voteit.se")
        data = response.json()
        self.assertEqual(response.status_code, 200, data)
        self.assertDictEqual(self.other_org_response, data)

    def test_list_host_regular_host(self):
        self.client.force_login(self.other_org_user)
        url = reverse("organisation-list")
        response = self.client.get(url, HTTP_HOST="other.voteit.se")
        data = response.json()
        self.assertEqual(response.status_code, 200, data)
        self.assertDictEqual(self.other_org_response, data)


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

    def test_user_id_in_filter(self):
        second_manager = self.organisation.users.create(username="second_manager")
        self.organisation.add_roles(second_manager, ROLE_MEETING_CREATOR)
        self.client.force_login(self.manager)
        response = self.client.get(
            self.list_url,
            {"user_id_in": f"{self.manager.pk},{second_manager.pk}"},
        )
        self.assertEqual(HTTPStatus.OK, response.status_code)
        self.assertEqual(
            {self.manager.pk, second_manager.pk},
            {item["user"]["pk"] for item in response.json()},
        )

    def test_user_id_in_filter_single(self):
        self.client.force_login(self.manager)
        response = self.client.get(
            self.list_url,
            {"user_id_in": str(self.manager.pk)},
        )
        self.assertEqual(HTTPStatus.OK, response.status_code)
        self.assertEqual(1, len(response.json()))
        self.assertEqual(self.manager.pk, response.json()[0]["user"]["pk"])


class OrganisationRolesChangeTests(APITestCase):
    add_url = reverse("organisationroles-add-roles")
    remove_url = reverse("organisationroles-remove-roles")

    @classmethod
    def setUpTestData(cls):
        cls.organisation = org = Organisation.objects.create(title="Test org")
        cls.manager = org.users.create(username="chg_manager")
        org.add_roles(cls.manager, ROLE_ORG_MANAGER)
        cls.member = org.users.create(username="chg_member")

    def _add_payload(self, user=None, roles=None):
        return {
            "user": (user or self.member).pk,
            "roles": roles or [str(ROLE_ORG_MANAGER)],
        }

    def test_add_unauthorized(self):
        response = self.client.post(self.add_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.UNAUTHORIZED, response.status_code)

    def test_add_member_forbidden(self):
        self.client.force_login(self.member)
        response = self.client.post(self.add_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.FORBIDDEN, response.status_code)

    def test_add_manager(self):
        self.client.force_login(self.manager)
        response = self.client.post(self.add_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.OK, response.status_code)
        self.assertIn(str(ROLE_ORG_MANAGER), response.json()["assigned"])

    def test_add_logs_change(self):
        self.client.force_login(self.manager)
        with self.assertLogs("voteit.event.roles") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(self.add_url, self._add_payload(), format="json")
                self.assertEqual(0, len(logs.records))
            self.assertEqual(1, len(logs.records))
        self.assertIn("Added", logs.records[0].getMessage())

    def test_add_bad_role(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            self.add_url, self._add_payload(roles=["jeff"]), format="json"
        )
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_add_user_from_other_org(self):
        other_org = Organisation.objects.create(title="Other org")
        other_user = other_org.users.create(username="org_alien")
        self.client.force_login(self.manager)
        response = self.client.post(
            self.add_url, self._add_payload(user=other_user), format="json"
        )
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_remove_unauthorized(self):
        response = self.client.post(self.remove_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.UNAUTHORIZED, response.status_code)

    def test_remove_member_forbidden(self):
        self.client.force_login(self.member)
        response = self.client.post(self.remove_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.FORBIDDEN, response.status_code)

    def test_remove_manager(self):
        self.organisation.add_roles(self.member, ROLE_ORG_MANAGER, ROLE_MEETING_CREATOR)
        self.client.force_login(self.manager)
        response = self.client.post(
            self.remove_url,
            self._add_payload(roles=[str(ROLE_MEETING_CREATOR)]),
            format="json",
        )
        self.assertEqual(HTTPStatus.OK, response.status_code)
        self.assertNotIn(str(ROLE_MEETING_CREATOR), response.json()["assigned"])

    def test_remove_last_role_returns_no_content(self):
        self.organisation.add_roles(self.member, ROLE_ORG_MANAGER)
        self.client.force_login(self.manager)
        response = self.client.post(self.remove_url, self._add_payload(), format="json")
        self.assertEqual(HTTPStatus.NO_CONTENT, response.status_code)

    def test_remove_logs_change(self):
        self.organisation.add_roles(self.member, ROLE_ORG_MANAGER)
        self.client.force_login(self.manager)
        with self.assertLogs("voteit.event.roles") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(self.remove_url, self._add_payload(), format="json")
                self.assertEqual(0, len(logs.records))
            self.assertEqual(1, len(logs.records))
        self.assertIn("Removed", logs.records[0].getMessage())

    def test_remove_bad_role(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            self.remove_url, self._add_payload(roles=["jeff"]), format="json"
        )
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_remove_user_from_other_org(self):
        other_org = Organisation.objects.create(title="Other org")
        other_user = other_org.users.create(username="org_alien2")
        self.client.force_login(self.manager)
        response = self.client.post(
            self.remove_url, self._add_payload(user=other_user), format="json"
        )
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)


class OrganisationRolesAvailableRolesTests(APITestCase):
    url = reverse("organisationroles-available")

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(title="Avail org")
        cls.member = cls.org.users.create(username="avail_member")

    def test_anonymous_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(HTTPStatus.OK, response.status_code)

    def test_returns_all_roles(self):
        self.client.force_login(self.member)
        response = self.client.get(self.url)
        names = {item["name"] for item in response.json()}
        self.assertEqual({str(ROLE_ORG_MANAGER), str(ROLE_MEETING_CREATOR)}, names)

    def test_no_predicate_info_in_response(self):
        self.client.force_login(self.member)
        response = self.client.get(self.url)
        for item in response.json():
            self.assertNotIn("predicate_info", item)

    def test_each_role_has_required_fields(self):
        self.client.force_login(self.member)
        response = self.client.get(self.url)
        for item in response.json():
            self.assertIn("name", item)
            self.assertIn("title", item)
            self.assertIn("description", item)
            self.assertIn("require_names", item)


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
