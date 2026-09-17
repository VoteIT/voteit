import base64
import hashlib
import json
import time
from types import SimpleNamespace
from urllib.parse import parse_qs
from urllib.parse import urlparse

import jwt
import responses
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase
from django.test import override_settings
from rest_framework.test import APITestCase
from social_django.storage import BaseDjangoStorage
from social_django.strategy import DjangoStrategy

from voteit.app.scouterna import SCOUTID_PROVIDER
from voteit.app.scouterna.backends import SCOUTNET_MEMBER_NO
from voteit.app.scouterna.backends import ScoutIDOpenIdConnect
from voteit.app.scouterna.testing import scoutid_enabled
from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation.models import Organisation

User = get_user_model()

ISSUER = "https://scoutid/realms/scoutnet"
OTHER_ISSUER = "https://other-scoutid/realms/scoutnet"


def _discovery_doc(issuer: str) -> dict:
    """
    The subset of Keycloak's discovery document that the backend reads.
    """
    base = f"{issuer}/protocol/openid-connect"
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{base}/auth",
        "token_endpoint": f"{base}/token",
        "userinfo_endpoint": f"{base}/userinfo",
        "jwks_uri": f"{base}/certs",
        "end_session_endpoint": f"{base}/logout",
        "revocation_endpoint": f"{base}/revoke",
        "token_endpoint_auth_methods_supported": ["client_secret_basic"],
    }


class _Realm:
    """
    A signing key plus the endpoints that go with one ScoutID realm.
    """

    def __init__(self, issuer: str = ISSUER, kid: str = "test-key"):
        self.issuer = issuer
        self.kid = kid
        self.private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048
        )
        self.config = _discovery_doc(issuer)

    def jwks(self) -> dict:
        key = json.loads(
            jwt.algorithms.RSAAlgorithm.to_jwk(self.private_key.public_key())
        )
        key.update({"kid": self.kid, "alg": "RS256", "use": "sig"})
        return {"keys": [key]}

    def id_token(self, client_id: str, nonce: str, **claims) -> str:
        payload = {
            "iss": self.issuer,
            "aud": client_id,
            "sub": "b4d3e2f1-0000-4000-8000-000000000001",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "nonce": nonce,
            "preferred_username": "scoutnet|9876543",
            "name": "Kim Scout",
            "given_name": "Kim",
            "family_name": "Scout",
            "picture": "https://scoutnet/avatar/9876543.png",
            "email": "kim@scoutkaren.example",
            "email_verified": True,
        }
        payload.update(claims)
        return jwt.encode(
            payload, self.private_key, algorithm="RS256", headers={"kid": self.kid}
        )

    def register(self, id_token: str, userinfo: dict | None = None):
        """
        Mock every call one login makes against this realm.
        """
        responses.add(
            responses.GET,
            f"{self.issuer}/.well-known/openid-configuration",
            json=self.config,
        )
        responses.add(responses.GET, self.config["jwks_uri"], json=self.jwks())
        responses.add(
            responses.POST,
            self.config["token_endpoint"],
            json={
                "access_token": "an-access-token",
                "id_token": id_token,
                "refresh_token": "a-refresh-token",
                "expires_in": 300,
                "token_type": "Bearer",
            },
        )
        if userinfo is not None:
            responses.add(
                responses.GET, self.config["userinfo_endpoint"], json=userinfo
            )


@scoutid_enabled()
class ScoutIDBackendTests(TestCase):
    """
    The parts that need no round trip: scopes, endpoint resolution, claims.
    """

    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.get(pk=1)
        cls.org.host = "testserver"
        cls.org.save()
        cls.provider = cls.org.providers.create(
            provider_id=SCOUTID_PROVIDER,
            scope="openid profile email",
            client_id="voteit",
            client_secret="s3cret",
        )

    def setUp(self):
        ScoutIDOpenIdConnect._oidc_config_for.invalidate()
        ScoutIDOpenIdConnect._jwks_keys_for.invalidate()

    def _backend(self):
        request = RequestFactory().get("/")
        request.session = self.client.session
        return ScoutIDOpenIdConnect(
            strategy=DjangoStrategy(BaseDjangoStorage, request=request)
        )

    def test_credentials_come_from_the_organisations_provider(self):
        self.assertEqual(("voteit", "s3cret"), self._backend().get_key_and_secret())

    def test_scope_merges_default_and_provider(self):
        self.provider.scope = "scoutnet-memberships phone"
        self.provider.save()
        self.assertEqual(
            ["email", "openid", "phone", "profile", "scoutnet-memberships"],
            self._backend().get_scope(),
        )

    def test_oidc_endpoint_defaults_to_the_dev_realm(self):
        self.assertEqual(
            "https://dev.id.scouterna.se/realms/scoutnet",
            self._backend().oidc_endpoint(),
        )

    def test_oidc_endpoint_from_provider_wins(self):
        self.provider.oidc_endpoint = "https://id.scouterna.se/realms/scoutnet/"
        self.provider.save()
        # Also checks that a trailing slash does not produce a double slash in
        # the discovery URL.
        self.assertEqual(
            "https://id.scouterna.se/realms/scoutnet",
            self._backend().oidc_endpoint(),
        )

    @override_settings(
        SOCIAL_AUTH_SCOUTID_OIDC_ENDPOINT="https://staging.scouterna/realms/scoutnet"
    )
    def test_oidc_endpoint_falls_back_to_setting(self):
        self.assertEqual(
            "https://staging.scouterna/realms/scoutnet",
            self._backend().oidc_endpoint(),
        )

    def test_login_url(self):
        self.assertEqual(
            "/login/scoutid/", ScoutIDOpenIdConnect.get_login_url(self.provider)
        )

    def test_profile_and_logout_urls_follow_the_realm(self):
        self.provider.oidc_endpoint = ISSUER
        self.assertEqual(
            f"{ISSUER}/account",
            ScoutIDOpenIdConnect.get_profile_url(self.provider),
        )
        self.assertEqual(
            f"{ISSUER}/protocol/openid-connect/logout",
            ScoutIDOpenIdConnect.get_logout_url(self.provider),
        )

    @responses.activate
    def test_logout_url_matches_the_realms_discovery_document(self):
        """
        Built rather than discovered, so assert the two agree.
        """
        realm = _Realm()
        responses.add(
            responses.GET,
            f"{ISSUER}/.well-known/openid-configuration",
            json=realm.config,
        )
        self.provider.oidc_endpoint = ISSUER
        self.provider.save()
        self.assertEqual(
            realm.config["end_session_endpoint"],
            ScoutIDOpenIdConnect.get_logout_url(self.provider),
        )

    def test_urls_use_the_default_realm_without_a_column(self):
        self.assertEqual(
            "https://dev.id.scouterna.se/realms/scoutnet/account",
            ScoutIDOpenIdConnect.get_profile_url(self.provider),
        )

    def test_missing_provider_row_is_an_auth_error(self):
        from social_core.exceptions import AuthException

        self.provider.delete()
        with self.assertRaises(AuthException):
            self._backend().get_key_and_secret()

    def test_get_user_details_maps_picture_to_img_url(self):
        details = self._backend().get_user_details(
            {
                "sub": "uuid",
                "preferred_username": "scoutnet|9876543",
                "given_name": "Kim",
                "family_name": "Scout",
                "name": "Kim Scout",
                "email": "kim@scoutkaren.example",
                "picture": "https://scoutnet/avatar/9876543.png",
            }
        )
        self.assertEqual("https://scoutnet/avatar/9876543.png", details["img_url"])
        self.assertEqual("Kim", details["first_name"])
        self.assertEqual("Scout", details["last_name"])
        self.assertEqual("kim@scoutkaren.example", details["email"])
        self.assertEqual("scoutnet|9876543", details["username"])

    def test_get_user_details_without_picture(self):
        details = self._backend().get_user_details({"sub": "uuid", "given_name": "Kim"})
        self.assertIsNone(details["img_url"])

    def _extra_data(self, **claims):
        response = {"access_token": "a-token", "expires_in": 300, **claims}
        return self._backend().extra_data("uuid", "uuid", response, {}, {})

    def test_member_no_comes_from_preferred_username(self):
        backend = self._backend()
        self.assertEqual(
            "9876543",
            backend.get_member_no({"preferred_username": "scoutnet|9876543"}),
        )

    def test_member_no_is_none_without_the_separator(self):
        backend = self._backend()
        with self.assertLogs("voteit.app.scouterna.backends", level="WARNING"):
            self.assertIsNone(backend.get_member_no({"preferred_username": "9876543"}))

    def test_member_no_is_none_without_the_claim(self):
        backend = self._backend()
        with self.assertLogs("voteit.app.scouterna.backends", level="WARNING"):
            self.assertIsNone(backend.get_member_no({}))

    def test_extra_data_stores_verified_email_and_member_no(self):
        data = self._extra_data(
            preferred_username="scoutnet|9876543",
            email="kim@scoutkaren.example",
            email_verified=True,
        )
        self.assertEqual(
            {
                "email": ["kim@scoutkaren.example"],
                SCOUTNET_MEMBER_NO: ["9876543"],
            },
            data["user_data"],
        )

    def test_extra_data_skips_an_unverified_email(self):
        """
        user_data decides invite matching and which address a user may set, so
        an address ScoutID will not vouch for has no business in it.
        """
        data = self._extra_data(
            preferred_username="scoutnet|9876543",
            email="kim@scoutkaren.example",
            email_verified=False,
        )
        self.assertEqual({SCOUTNET_MEMBER_NO: ["9876543"]}, data["user_data"])

    def test_extra_data_reads_claims_from_the_id_token(self):
        """
        A realm may put the claims in the id token rather than in userinfo.
        """
        backend = self._backend()
        backend.id_token = {
            "preferred_username": "scoutnet|9876543",
            "email": "kim@scoutkaren.example",
            "email_verified": True,
        }
        data = backend.extra_data(
            "uuid", "uuid", {"access_token": "a-token", "expires_in": 300}, {}, {}
        )
        self.assertEqual(
            {"email": ["kim@scoutkaren.example"], SCOUTNET_MEMBER_NO: ["9876543"]},
            data["user_data"],
        )

    def test_identity_data_reads_back_what_extra_data_stored(self):
        social = SimpleNamespace(
            extra_data=self._extra_data(
                preferred_username="scoutnet|9876543",
                email="kim@scoutkaren.example",
                email_verified=True,
            )
        )
        self.assertEqual(
            {"email": ["kim@scoutkaren.example"], SCOUTNET_MEMBER_NO: ["9876543"]},
            ScoutIDOpenIdConnect.get_identity_data(social),
        )

    @responses.activate
    def test_discovery_is_cached_per_realm(self):
        """
        social_core caches ``oidc_config`` on the backend class, so two tenants on
        different realms would otherwise read each other's issuer.
        """
        realm = _Realm()
        other = _Realm(issuer=OTHER_ISSUER)
        responses.add(
            responses.GET,
            f"{ISSUER}/.well-known/openid-configuration",
            json=realm.config,
        )
        responses.add(
            responses.GET,
            f"{OTHER_ISSUER}/.well-known/openid-configuration",
            json=other.config,
        )
        # A fresh backend each time, as a second request would get -- but the
        # discovery cache they share lives on the class.
        self.provider.oidc_endpoint = ISSUER
        self.provider.save()
        self.assertEqual(ISSUER, self._backend().id_token_issuer())

        self.provider.oidc_endpoint = OTHER_ISSUER
        self.provider.save()
        self.assertEqual(OTHER_ISSUER, self._backend().id_token_issuer())


@scoutid_enabled()
@override_settings(
    LANGUAGE_CODE="en-us",
    SOCIAL_AUTH_ALLOWED_REDIRECT_HOSTS=["testing"],
    SOCIAL_AUTH_RAISE_EXCEPTIONS=True,
)
class ScoutIDLoginTests(APITestCase):
    """
    The whole authorization code flow, against a mocked Keycloak realm.
    """

    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.get(pk=1)
        cls.org.host = "testserver"
        cls.org.save()
        cls.provider = cls.org.providers.create(
            provider_id=SCOUTID_PROVIDER,
            scope="openid profile email",
            client_id="voteit",
            client_secret="s3cret",
            oidc_endpoint=ISSUER,
        )

    def setUp(self):
        ScoutIDOpenIdConnect._oidc_config_for.invalidate()
        ScoutIDOpenIdConnect._jwks_keys_for.invalidate()
        self.realm = _Realm()

    def _begin(self) -> tuple[str, str]:
        """
        Start a login and return the ``state`` and ``nonce`` handed to Keycloak.
        """
        responses.add(
            responses.GET,
            f"{ISSUER}/.well-known/openid-configuration",
            json=self.realm.config,
        )
        response = self.client.get("/login/scoutid/")
        self.assertEqual(302, response.status_code)
        location = response.get("Location")
        self.assertTrue(
            location.startswith(self.realm.config["authorization_endpoint"])
        )
        params = parse_qs(urlparse(location).query)
        self.challenge = params.get("code_challenge", [None])[0]
        return params["state"][0], params["nonce"][0]

    @responses.activate
    def test_begin_uses_discovered_endpoint_and_org_credentials(self):
        responses.add(
            responses.GET,
            f"{ISSUER}/.well-known/openid-configuration",
            json=self.realm.config,
        )
        response = self.client.get("/login/scoutid/")
        params = parse_qs(urlparse(response.get("Location")).query)
        self.assertEqual(["voteit"], params["client_id"])
        self.assertEqual(["code"], params["response_type"])
        self.assertEqual(["email openid profile"], params["scope"])
        self.assertTrue(params["nonce"][0])

    @responses.activate
    def test_begin_sends_a_pkce_challenge(self):
        responses.add(
            responses.GET,
            f"{ISSUER}/.well-known/openid-configuration",
            json=self.realm.config,
        )
        response = self.client.get("/login/scoutid/")
        params = parse_qs(urlparse(response.get("Location")).query)
        self.assertEqual(["S256"], params["code_challenge_method"])
        self.assertTrue(params["code_challenge"][0])

    @responses.activate
    def test_complete_sends_the_code_verifier(self):
        state, nonce = self._begin()
        self.realm.register(
            self.realm.id_token("voteit", nonce),
            userinfo={"sub": "b4d3e2f1-0000-4000-8000-000000000001"},
        )
        self.client.get("/complete/scoutid/", data={"state": state, "code": "code"})
        token_request = next(
            call.request
            for call in responses.calls
            if call.request.url == self.realm.config["token_endpoint"]
        )
        body = parse_qs(token_request.body)
        self.assertTrue(body["code_verifier"][0])
        # The verifier must hash to the challenge the authorization request sent.
        verifier = body["code_verifier"][0]
        digest = hashlib.sha256(verifier.encode()).digest()
        expected = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        self.assertEqual(expected, self.challenge)

    @responses.activate
    def test_complete_creates_user(self):
        state, nonce = self._begin()
        id_token = self.realm.id_token("voteit", nonce)
        self.realm.register(
            id_token,
            userinfo={
                "sub": "b4d3e2f1-0000-4000-8000-000000000001",
                "preferred_username": "scoutnet|9876543",
                "name": "Kim Scout",
                "given_name": "Kim",
                "family_name": "Scout",
                "picture": "https://scoutnet/avatar/9876543.png",
                "email": "kim@scoutkaren.example",
                "email_verified": True,
            },
        )
        response = self.client.get(
            "/complete/scoutid/", data={"state": state, "code": "auth-code"}
        )
        self.assertEqual(302, response.status_code)
        self.assertEqual(settings.LOGIN_REDIRECT_URL, response.get("Location"))

        user = User.objects.get(social_auth__uid="b4d3e2f1-0000-4000-8000-000000000001")
        self.assertEqual(self.org, user.organisation)
        # identity_id is the id proxy's namespace; this account has none.
        self.assertIsNone(user.identity_id)
        self.assertEqual("Kim", user.first_name)
        self.assertEqual("Scout", user.last_name)
        self.assertEqual("kim@scoutkaren.example", user.email)
        self.assertEqual("https://scoutnet/avatar/9876543.png", user.img_url)
        # The '|' in scoutnet|9876543 is not a legal Django username character.
        self.assertEqual("scoutnet9876543", user.username)

        social = user.social_auth.get()
        self.assertEqual(SCOUTID_PROVIDER, social.provider)
        self.assertEqual("b4d3e2f1-0000-4000-8000-000000000001", social.uid)

    @responses.activate
    def test_complete_stores_what_scoutid_vouches_for(self):
        """
        ``user_data`` is what ``get_user_identity_data`` reads, so the whole
        round trip has to land it -- not just the unit-tested ``extra_data``.
        """
        state, nonce = self._begin()
        self.realm.register(
            self.realm.id_token("voteit", nonce),
            userinfo={
                "sub": "b4d3e2f1-0000-4000-8000-000000000001",
                "preferred_username": "scoutnet|9876543",
                "email": "kim@scoutkaren.example",
                "email_verified": True,
            },
        )
        self.client.get("/complete/scoutid/", data={"state": state, "code": "code"})
        social = User.objects.get(
            social_auth__uid="b4d3e2f1-0000-4000-8000-000000000001"
        ).social_auth.get()
        self.assertEqual(
            {
                "email": ["kim@scoutkaren.example"],
                SCOUTNET_MEMBER_NO: ["9876543"],
            },
            social.extra_data["user_data"],
        )

    @responses.activate
    def test_connecting_scoutid_keeps_the_id_proxy_identity(self):
        """
        Someone logged in with the id proxy connecting their ScoutID: the
        credential attaches to the account they already have, and identity_id
        -- which is the *person*, and what groups their accounts -- stays put.
        """
        existing = self.org.users.create(
            username="kim", identity_id="an-id-proxy-identity", is_active=True
        )
        existing.social_auth.create(
            provider=IDPROXY_PROVIDER, uid="an-id-proxy-identity", extra_data={}
        )
        self.client.force_login(existing)

        state, nonce = self._begin()
        self.realm.register(
            self.realm.id_token("voteit", nonce),
            userinfo={"sub": "b4d3e2f1-0000-4000-8000-000000000001"},
        )
        response = self.client.get(
            "/complete/scoutid/", data={"state": state, "code": "auth-code"}
        )
        self.assertEqual(302, response.status_code)

        existing.refresh_from_db()
        self.assertEqual("an-id-proxy-identity", existing.identity_id)
        self.assertEqual(
            {IDPROXY_PROVIDER, SCOUTID_PROVIDER},
            set(existing.social_auth.values_list("provider", flat=True)),
        )
        # No second account was created for the same person.
        self.assertEqual(1, self.org.users.filter(username="kim").count())

    @responses.activate
    def test_an_identity_id_matching_the_sub_is_not_adopted(self):
        """
        identity_id is an id proxy identifier. A value in it that happens to
        equal a Keycloak sub is a collision between namespaces, not the same
        person, so this login gets its own account -- matching it to an existing
        one is the account matcher's job, on evidence it can actually check.
        """
        existing = self.org.users.create(
            username="scoutnet9876543",
            identity_id="b4d3e2f1-0000-4000-8000-000000000001",
            is_active=True,
        )
        state, nonce = self._begin()
        self.realm.register(
            self.realm.id_token("voteit", nonce),
            userinfo={"sub": "b4d3e2f1-0000-4000-8000-000000000001"},
        )
        response = self.client.get(
            "/complete/scoutid/", data={"state": state, "code": "auth-code"}
        )
        self.assertEqual(302, response.status_code)
        self.assertEqual(0, existing.social_auth.count())
        created = User.objects.get(
            social_auth__uid="b4d3e2f1-0000-4000-8000-000000000001"
        )
        self.assertNotEqual(existing, created)
        self.assertIsNone(created.identity_id)

    @responses.activate
    def test_complete_does_not_clear_email(self):
        """
        ``remove_nonmatching_email`` reads the id proxy's ``user_data``, which
        ScoutID does not send. It must leave ScoutID logins alone rather than
        read the absent key as "no addresses known".
        """
        state, nonce = self._begin()
        self.realm.register(
            self.realm.id_token("voteit", nonce),
            userinfo={
                "sub": "b4d3e2f1-0000-4000-8000-000000000001",
                "email": "kim@scoutkaren.example",
                "given_name": "Kim",
                "family_name": "Scout",
                "preferred_username": "scoutnet|9876543",
            },
        )
        self.client.get("/complete/scoutid/", data={"state": state, "code": "code"})
        user = User.objects.get(social_auth__uid="b4d3e2f1-0000-4000-8000-000000000001")
        self.assertEqual("kim@scoutkaren.example", user.email)

    @responses.activate
    def test_complete_rejects_wrong_issuer(self):
        from social_core.exceptions import AuthTokenError

        state, nonce = self._begin()
        self.realm.register(
            self.realm.id_token("voteit", nonce, iss=OTHER_ISSUER),
            userinfo={"sub": "b4d3e2f1-0000-4000-8000-000000000001"},
        )
        with self.assertRaises(AuthTokenError):
            self.client.get("/complete/scoutid/", data={"state": state, "code": "code"})

    @responses.activate
    def test_complete_rejects_wrong_nonce(self):
        from social_core.exceptions import AuthTokenError

        state, _nonce = self._begin()
        self.realm.register(
            self.realm.id_token("voteit", "not-the-nonce"),
            userinfo={"sub": "b4d3e2f1-0000-4000-8000-000000000001"},
        )
        with self.assertRaises(AuthTokenError):
            self.client.get("/complete/scoutid/", data={"state": state, "code": "code"})

    @responses.activate
    def test_complete_rejects_inactive_organisation(self):
        from social_core.exceptions import AuthException

        state, nonce = self._begin()
        self.realm.register(
            self.realm.id_token("voteit", nonce),
            userinfo={"sub": "b4d3e2f1-0000-4000-8000-000000000001"},
        )
        Organisation.objects.filter(pk=self.org.pk).update(active=False)
        with self.assertRaises(AuthException):
            self.client.get("/complete/scoutid/", data={"state": state, "code": "code"})
