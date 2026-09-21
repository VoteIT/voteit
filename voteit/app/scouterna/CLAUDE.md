# voteit.app.scouterna

Customer app for **Scouterna** — Guides and Scouts of Sweden. Its only content today
is `ScoutIDOpenIdConnect`, a Python Social Auth backend for **ScoutID**, Scouterna's
Keycloak-based identity service. Members sign in with their [Scoutnet](https://scoutnet.se)
credentials.

Integrator documentation lives in the
[scoutid-keycloak wiki](https://github.com/Scouterna/scoutid-keycloak/wiki).

## The backend (`backends.py`)

`ScoutIDOpenIdConnect` subclasses `social_core`'s generic `OpenIdConnectAuth` and mixes
in `voteit.organisation.backends.OrganisationBackendMixin`, which is what makes it
multi-tenant: the `Organisation` comes from the request's `Host` header, and its
credentials from that organisation's `OAuth2Provider` row with
`provider_id="scoutid"`.

- `name = "scoutid"` (exported as `SCOUTID_PROVIDER` from `__init__.py`). Login entry
  point is `/login/scoutid/`, callback `/complete/scoutid/`.
- `OIDC_ENDPOINT` defaults to the **development** realm,
  `https://dev.id.scouterna.se/realms/scoutnet`. Production (`https://id.scouterna.se`)
  is not live yet — the wiki says everything but the base URL stays the same.
- `DEFAULT_SCOPE = ["openid", "profile", "email"]`, merged with the org's
  `provider.scope` by the mixin.
- `DEFAULT_USE_PKCE = True` — see below.
- `ID_KEY = "sub"` — a Keycloak UUID, stored as `UserSocialAuth.uid`. It never reaches
  `User.identity_id`: that column holds an id proxy identifier and nothing else, so a
  ScoutID-only account has no `identity_id` at all and is reached through its credential.
  See `voteit/organisation/CLAUDE.md`.

### Endpoint resolution order

`get_issuer(provider)` prefers, in order:

1. `OAuth2Provider.oidc_endpoint` — per organisation, editable in the admin, so moving a
   tenant from dev to production is a data change rather than a deploy.
2. `SOCIAL_AUTH_SCOUTID_OIDC_ENDPOINT` — picked up free by the `SOCIAL_AUTH_*` env loop
   in `project/settings.py`.
3. `OIDC_ENDPOINT`, the dev realm.

It is a classmethod because `get_profile_url` / `get_logout_url` are called while
serialising an organisation, where there is no strategy to read settings through;
`oidc_endpoint()` just delegates to it.

Everything else (authorization, token, userinfo, JWKS, issuer) is discovered from
`<endpoint>/.well-known/openid-configuration`.

### URLs offered to the SPA

| Hook | Value |
|---|---|
| `get_login_url` | `/login/scoutid/` (the `social_django` default) |
| `get_profile_url` | `<issuer>/account` — Keycloak's account console |
| `get_logout_url` | `<issuer>/protocol/openid-connect/logout` |

The last two are **built from the issuer, not discovered**. Discovery would put an
outbound HTTP call on the path of every `/api/organisation/` response and make it
depend on Keycloak being reachable. Both paths are fixed Keycloak conventions;
`test_logout_url_matches_the_realms_discovery_document` asserts the built logout URL
equals the realm's advertised `end_session_endpoint`, so the shortcut cannot drift
silently.

## Claims

From the default scopes — see the wiki's
[ScoutID Data Reference](https://github.com/Scouterna/scoutid-keycloak/wiki/ScoutID-Data-Reference):

| Claim | Lands on |
|---|---|
| `sub` | `UserSocialAuth.uid` (**not** `User.identity_id` — see above) |
| `preferred_username` | `User.username`, after cleaning |
| `given_name` / `family_name` | `User.first_name` / `last_name` |
| `picture` | `User.img_url` (mapped in `get_user_details`) |
| `email` | `User.email` |

`preferred_username` is always `scoutnet|<member_no>`. The `|` is not a legal Django
username character, so `social_core`'s `clean_username` strips it and the stored username
is `scoutnet9876543`.

The `scoutnet-memberships` scope carries groups, troops and roles. Nothing reads it, so
it is deliberately **not** requested — adding it would park a pile of personal data in
`UserSocialAuth.extra_data` for no gain. Add it to `provider.scope` when something
consumes it.

## What this backend vouches for

`extra_data()` writes a `user_data` dict in the id proxy's `{scope: [value, ...]}` shape,
which is what `OrganisationBackendMixin.get_identity_data` reads for every backend and
`voteit.organisation.utils.get_user_identity_data` merges across them:

| Key | Source |
|---|---|
| `email` | the `email` claim, **only when `email_verified` is true** |
| `scoutnet_member_no` | the number in `preferred_username`, via `get_member_no()` |

That dict decides which invites a user matches and which address they may set on their
profile (`UserSerializer.validate_email`), so an address ScoutID will not vouch for has no
business in it.

`MEMBER_ID_KEY = SCOUTNET_MEMBER_NO` marks the membership number as this backend's member
id, so invites with a `member_id` column match it. See `voteit/organisation/CLAUDE.md`.

`_claim()` reads a claim from userinfo and falls back to the id token, the way
`OpenIdConnectAuth.get_user_details` does — a realm may put them in either.

## Non-obvious design decisions

**The discovery and JWKS caches are re-keyed by URL.** `OpenIdConnectAuth` decorates
`oidc_config()` and `get_jwks_keys()` with `social_core.utils.cache`, whose key is
`(class, args, kwargs)` — the *class*, not the instance. Since the endpoint is per
organisation here, every tenant on this backend would otherwise share one cache entry,
and two tenants on different realms would read each other's issuer and verify against
each other's signing keys. `_oidc_config_for(endpoint)` and `_jwks_keys_for(jwks_uri)`
take the URL as an argument so it lands in the cache key.
`get_jwks_keys.invalidate` is re-pointed at `_jwks_keys_for`'s cache, because
`find_valid_key` calls it to pick up a rotated signing key.
`ScoutIDBackendTests.test_discovery_is_cached_per_realm` covers this; it fails against
the unmodified library behaviour.

**PKCE is on, via `DEFAULT_USE_PKCE = True`.** `BaseOAuth2PKCE` enables PKCE by default,
but `OpenIdConnectAuth` turns it back off, so the subclass has to re-enable it.
`auth_params()` reads `self.setting("USE_PKCE", default=self.DEFAULT_USE_PKCE)`, so the
class attribute is the switch and `SOCIAL_AUTH_SCOUTID_USE_PKCE` still overrides it.
The challenge method is `S256`, which the realm advertises under
`code_challenge_methods_supported`.

VoteIT is a confidential client, so it sends PKCE *and* the client secret — Keycloak
accepts both together, and it protects the authorization code in transit regardless.

Careful with the override: `project/settings.py` copies every `SOCIAL_AUTH_*` env var in
as a **string**, so `SOCIAL_AUTH_SCOUTID_USE_PKCE=false` from the environment is the
truthy string `"false"`. Set it in a settings module, not the env, if you ever need it
off.

**`remove_nonmatching_email` skips this backend.** That pipeline step reads the id
proxy's `user_data` structure. ScoutID does not send one, and an absent key would read as
"the identity server knows no addresses" — silently clearing the user's email on every
login. The step now early-returns for anything but `idproxy`.

**Scoutnet stays the source of the data.** `get_profile_url` points at Keycloak's
account console, which is where a user manages the *login*. Membership data itself
lives in Scoutnet.

## Setup

1. Request a client from `scoutid@scouterna.se` (see the wiki's Home page) with the
   redirect URI `https://<org host>/complete/scoutid/`. Self-service registration is
   planned for September 2026; until then the
   [scoutid-keycloak-provider](https://github.com/Scouterna/scoutid-keycloak-provider)
   repo has a local Docker Compose setup with a pre-configured test client.
2. Add an `OAuth2Provider` in the admin for the organisation, with
   `provider_id="scoutid"`, the client id and secret, and scope `openid profile email`.
3. The organisation's `/api/organisation/` payload then lists it under `providers`, and
   the SPA can offer its `login_url`.

## Tests

```
POSTGRES_PORT=5433 python manage.py test voteit.app.scouterna --keepdb --failfast
```

Both test classes are decorated with `@scoutid_enabled()` from `testing.py`, which adds
this backend to `AUTHENTICATION_BACKENDS` for the duration. voteit ships as a package and
a deployment may leave the backend out, so the tests must not depend on the running
settings having it — they pass either way.

This works only because `voteit.organisation.signals.reload_social_backends` refreshes
social_core's backend cache on `setting_changed`. See that app's CLAUDE.md.

- `tests/test_backends.py` — credential and scope resolution, endpoint precedence, the
  login/profile/logout URLs, claim mapping, the per-realm cache, plus the full
  authorization code flow against a mocked Keycloak realm (`_Realm` generates an RSA key,
  serves a JWKS and signs id tokens, so signature, issuer and nonce validation all run
  for real).
- `tests/test_docs.py` — doctests in `backends.py`.
