from __future__ import annotations

import tempfile
from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils.http import urlencode
from django.utils.timezone import now
from rest_framework.test import APITestCase

from voteit.core.testing import run_permission_tests
from voteit.organisation.models import GlobalTermsOfService
from voteit.organisation.models import Organisation
from voteit.organisation.models import TermsOfService
from voteit.organisation.models import UserAccept
from voteit.organisation.rest_api.serializers import OrganisationSerializer
from voteit.organisation.roles import ROLE_MEETING_CREATOR
from voteit.organisation.roles import ROLE_ORG_MANAGER
from voteit.organisation.utils import accept_tos

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
            "colors": {},
            "components": [],
            "help_info": "",
            "logo": None,
            "page_title": "Other org",
            "providers": [],
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
            "colors": {},
            "components": [],
            "help_info": "",
            "logo": None,
            "page_title": "Test org",
            "pk": self.org.pk,
            "providers": [],
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


_LOGO = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    b'<rect width="10" height="10"/></svg>'
)


@override_settings(ID_HOST="https://testserver")
class OrganisationBrandingTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org: Organisation = Organisation.objects.create(
            title="Test org", host="testserver"
        )
        cls.manager = cls.org.users.create(username="manager")
        cls.user = cls.org.users.create(username="user")
        cls.org.add_roles(cls.manager, ROLE_ORG_MANAGER)
        cls.url = reverse("organisation-change")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._tmp.name)
        self._override.enable()

    def tearDown(self):
        self._override.disable()
        self._tmp.cleanup()

    def _upload(self, content=_LOGO, name="logo.svg"):
        return self.client.patch(
            self.url,
            data={
                "logo": SimpleUploadedFile(name, content, content_type="image/svg+xml")
            },
            format="multipart",
        )

    def test_colors(self):
        colors = {"appBar": {"r": 0, "g": 128, "b": 255}}
        for func, params in run_permission_tests(
            self,
            url=self.url,
            data={"colors": colors},
            method="PATCH",
            expected=(
                (self.manager, 200, {"colors": colors}),
                (self.user, 403),
                (None, 401),
            ),
        ):
            func(*params)

    def test_colors_saved(self):
        self.client.force_login(self.manager)
        colors = {"appBar": {"r": 1, "g": 2, "b": 3}}
        response = self.client.patch(self.url, {"colors": colors}, format="json")
        self.assertEqual(200, response.status_code)
        self.org.refresh_from_db()
        self.assertEqual(colors, self.org.colors)

    def test_colors_empty(self):
        self.client.force_login(self.manager)
        response = self.client.patch(self.url, {"colors": {}}, format="json")
        self.assertEqual(200, response.status_code)

    def test_colors_invalid(self):
        self.client.force_login(self.manager)
        for colors in (
            {"appBar": {"r": 256, "g": 0, "b": 0}},
            {"appBar": {"r": -1, "g": 0, "b": 0}},
            {"appBar": {"r": "1", "g": 0, "b": 0}},
            {"appBar": {"r": 1.5, "g": 0, "b": 0}},
            {"appBar": {"r": 0, "g": 0}},
            {"appBar": {"r": 0, "g": 0, "b": 0, "a": 1}},
            {"appBar": "#ff0000"},
            {"other": 1},
            ["appBar"],
            "x",
        ):
            with self.subTest(colors=colors):
                response = self.client.patch(
                    self.url, {"colors": colors}, format="json"
                )
                self.assertEqual(400, response.status_code)
                self.assertIn("colors", response.json())

    def test_logo_upload(self):
        self.client.force_login(self.manager)
        response = self._upload(name="whatever.png")
        self.assertEqual(200, response.status_code)
        logo = response.json()["logo"]
        self.assertIn(f"org_{self.org.pk}/logo/", logo)
        self.assertTrue(logo.endswith(".svg"))

    def test_logo_url_same_without_request(self):
        self.client.force_login(self.manager)
        logo = self._upload().json()["logo"]
        self.assertTrue(logo.startswith("/media/org_"))
        self.org.refresh_from_db()
        # What the organisation.changed push sends
        self.assertEqual(logo, OrganisationSerializer(self.org).data["logo"])

    def test_logo_upload_forbidden(self):
        self.client.force_login(self.user)
        self.assertEqual(403, self._upload().status_code)

    def test_logo_invalid(self):
        self.client.force_login(self.manager)
        response = self._upload(
            b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>'
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("logo", response.json())
        self.org.refresh_from_db()
        self.assertFalse(self.org.logo)

    def test_logo_remove(self):
        self.client.force_login(self.manager)
        self._upload()
        response = self.client.patch(self.url, {"logo": None}, format="json")
        self.assertEqual(200, response.status_code)
        self.assertIsNone(response.json()["logo"])


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


class GlobalTermsOfServiceViewSetTests(APITestCase):
    list_url = reverse("global-terms-of-service-list")

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(title="Test org", host="testserver")
        cls.user = cls.org.users.create(username="user")
        cls.old = GlobalTermsOfService.objects.create(
            body="Old",
            version=now() - timedelta(days=10),
            required_from=now().date() - timedelta(days=10),
        )
        cls.new = GlobalTermsOfService.objects.create(
            body="New", notes="Why", required_from=now().date()
        )
        cls.draft = GlobalTermsOfService.objects.create(
            body="Draft", version=now() + timedelta(minutes=1)
        )

    def test_list(self):
        for func, params in run_permission_tests(
            self,
            url=self.list_url,
            expected=((None, 200), (self.user, 200)),
        ):
            func(*params)

    def test_list_latest_first(self):
        response = self.client.get(self.list_url)
        self.assertEqual([self.new.pk, self.old.pk], [x["pk"] for x in response.json()])

    def test_draft_not_visible(self):
        url = reverse("global-terms-of-service-detail", kwargs={"pk": self.draft.pk})
        self.assertEqual(404, self.client.get(url).status_code)

    def test_retrieve(self):
        url = reverse("global-terms-of-service-detail", kwargs={"pk": self.old.pk})
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual({"pk", "body", "version", "required_from", "notes"}, set(data))
        self.assertEqual("Old", data["body"])
        self.assertEqual(self.old.required_from.isoformat(), data["required_from"])

    def test_read_only(self):
        self.client.force_login(self.user)
        response = self.client.post(self.list_url, data={"body": "Nope"})
        self.assertEqual(405, response.status_code)


class TermsOfServiceViewSetTests(APITestCase):
    list_url = reverse("terms-of-service-list")
    current_url = reverse("terms-of-service-current")
    accept_url = reverse("terms-of-service-accept")

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(title="Test org", host="testserver")
        cls.manager = cls.org.users.create(username="manager")
        cls.org.add_roles(cls.manager, ROLE_ORG_MANAGER)
        cls.user = cls.org.users.create(username="user")
        cls.other_org = Organisation.objects.create(
            title="Other org", host="other.voteit.se"
        )
        cls.gtos = GlobalTermsOfService.objects.create(
            body="Global",
            version=now() - timedelta(days=10),
            required_from=now().date() - timedelta(days=10),
        )
        cls.old = cls.org.tos.create(body="Old", version=now() - timedelta(days=5))
        cls.current = cls.org.tos.create(
            body="Current", version=now() - timedelta(days=1)
        )
        cls.future = cls.org.tos.create(
            body="Future", version=now() + timedelta(days=1)
        )
        cls.other_org.tos.create(body="Other")

    def _pks(self, response):
        return [x["pk"] for x in response.json()]

    def test_list(self):
        for func, params in run_permission_tests(
            self,
            url=self.list_url,
            expected=((None, 200), (self.user, 200), (self.manager, 200)),
        ):
            func(*params)

    def test_list_only_active_for_non_managers(self):
        response = self.client.get(self.list_url)
        self.assertEqual([self.current.pk], self._pks(response))
        self.client.force_login(self.user)
        self.assertEqual([self.current.pk], self._pks(self.client.get(self.list_url)))

    def test_list_all_for_managers(self):
        self.client.force_login(self.manager)
        response = self.client.get(self.list_url)
        self.assertEqual(
            [self.future.pk, self.current.pk, self.old.pk], self._pks(response)
        )

    def test_list_nothing_active(self):
        self.current.delete()
        self.old.delete()
        self.assertEqual([], self.client.get(self.list_url).json())

    def test_retrieve_old_version(self):
        url = reverse("terms-of-service-detail", kwargs={"pk": self.old.pk})
        for func, params in run_permission_tests(
            self,
            url=url,
            expected=((None, 404), (self.user, 404), (self.manager, 200)),
        ):
            func(*params)

    def test_create(self):
        for func, params in run_permission_tests(
            self,
            url=self.list_url,
            method="post",
            data={"body": "New"},
            expected=((None, 401), (self.user, 403)),
        ):
            func(*params)
        self.client.force_login(self.manager)
        response = self.client.post(self.list_url, {"body": "New"})
        self.assertEqual(201, response.status_code, response.json())
        tos = TermsOfService.objects.get(pk=response.json()["pk"])
        self.assertEqual(self.org, tos.organisation)
        self.assertEqual("New", tos.body)

    def test_create_ignores_version(self):
        self.client.force_login(self.manager)
        before = now()
        response = self.client.post(
            self.list_url,
            {"body": "New", "version": (before + timedelta(days=5)).isoformat()},
        )
        self.assertEqual(201, response.status_code, response.json())
        tos = TermsOfService.objects.get(pk=response.json()["pk"])
        self.assertLess(tos.version, before + timedelta(minutes=1))

    def test_create_without_global(self):
        self.client.force_login(self.manager)
        self.gtos.delete()
        response = self.client.post(self.list_url, {"body": "New"})
        self.assertEqual(201, response.status_code)

    def test_patch_body_only(self):
        url = reverse("terms-of-service-detail", kwargs={"pk": self.current.pk})
        data = {"body": "Fixed", "version": now().isoformat()}
        for func, params in run_permission_tests(
            self,
            url=url,
            method="patch",
            data=data,
            expected=(
                (None, 401),
                (self.user, 403),
                (self.manager, 200, {"body": "Fixed"}),
            ),
        ):
            func(*params)
        self.client.force_login(self.manager)
        self.client.patch(url, data, format="json")
        version = self.current.version
        self.current.refresh_from_db()
        self.assertEqual("Fixed", self.current.body)
        self.assertEqual(version, self.current.version)

    def test_delete_not_allowed(self):
        url = reverse("terms-of-service-detail", kwargs={"pk": self.current.pk})
        self.client.force_login(self.manager)
        self.assertEqual(405, self.client.delete(url).status_code)

    def test_current(self):
        for func, params in run_permission_tests(
            self,
            url=self.current_url,
            expected=((None, 200), (self.user, 200), (self.manager, 200)),
        ):
            func(*params)
        data = self.client.get(self.current_url).json()
        self.assertEqual(
            {
                "global_tos",
                "organisation_tos",
                "version",
                "accepted",
                "must_accept",
                "newer_global_tos",
            },
            set(data),
        )
        self.assertEqual(self.gtos.pk, data["global_tos"]["pk"])
        self.assertEqual(self.current.pk, data["organisation_tos"]["pk"])
        self.assertEqual(self.current.version, parse_datetime(data["version"]))
        self.assertIsNone(data["accepted"])
        self.assertTrue(data["must_accept"])
        self.assertFalse(data["newer_global_tos"])

    def test_current_accepted(self):
        accept_tos(self.user)
        self.client.force_login(self.user)
        data = self.client.get(self.current_url).json()
        self.assertIsNotNone(data["accepted"])
        self.assertFalse(data["must_accept"])

    def test_current_upcoming_global(self):
        # Not shown until required, or until the org publishes newer terms
        accept_tos(self.user)
        upcoming = GlobalTermsOfService.objects.create(
            version=now() - timedelta(days=2),
            required_from=now().date() + timedelta(days=5),
        )
        self.client.force_login(self.user)
        data = self.client.get(self.current_url).json()
        self.assertEqual(upcoming.pk, data["global_tos"]["pk"])
        self.assertEqual(self.current.version, parse_datetime(data["version"]))
        self.assertFalse(data["must_accept"])
        self.assertFalse(data["newer_global_tos"])
        upcoming.version = now()
        upcoming.save()
        data = self.client.get(self.current_url).json()
        self.assertEqual(self.gtos.pk, data["global_tos"]["pk"])
        self.assertFalse(data["must_accept"])
        self.assertTrue(data["newer_global_tos"])

    def test_current_only_org(self):
        self.gtos.delete()
        data = self.client.get(self.current_url).json()
        self.assertIsNone(data["global_tos"])
        self.assertEqual(self.current.pk, data["organisation_tos"]["pk"])

    def test_current_only_global(self):
        self.org.tos.all().delete()
        data = self.client.get(self.current_url).json()
        self.assertIsNone(data["organisation_tos"])
        self.assertEqual(self.gtos.version, parse_datetime(data["version"]))
        self.assertTrue(data["must_accept"])
        self.assertFalse(data["newer_global_tos"])

    def test_current_nothing(self):
        self.gtos.delete()
        self.org.tos.all().delete()
        data = self.client.get(self.current_url).json()
        self.assertIsNone(data["version"])
        self.assertFalse(data["must_accept"])

    def test_accept(self):
        data = {"version": self.current.version.isoformat()}
        for func, params in run_permission_tests(
            self,
            url=self.accept_url,
            method="post",
            data=data,
            expected=((None, 401), (self.user, 200), (self.manager, 200)),
        ):
            func(*params)
        self.client.force_login(self.user)
        response = self.client.post(self.accept_url, data)
        self.assertEqual(
            UserAccept.objects.get(user=self.user).accepted,
            parse_datetime(response.json()["accepted"]),
        )

    def test_accept_replaces_previous(self):
        old = accept_tos(self.user)
        self.client.force_login(self.user)
        self.client.post(self.accept_url, {"version": self.current.version.isoformat()})
        new = UserAccept.objects.get(user=self.user)
        self.assertEqual(old.pk, new.pk)
        self.assertGreater(new.accepted, old.accepted)

    def test_accept_outdated_version(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.accept_url, {"version": self.old.version.isoformat()}
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("version", response.json())
        self.assertEqual(400, self.client.post(self.accept_url).status_code)
        self.assertFalse(UserAccept.objects.exists())
