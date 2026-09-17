# voteit.organisation

Manages the top-level tenant (`Organisation`) and everything directly owned by it: org-level role assignments, terms of service, OAuth2/SSO configuration, and the identity proxy integration (Python Social Auth). Every user and every meeting in the system belongs to exactly one organisation. The app also owns the `IDProxyOAuth2` PSA backend and the full authentication pipeline that maps external identities to local users.

## Models

### Organisation
The root tenant. Key fields:
- `host` — unique hostname (e.g. `"meeting.myorg.se"`). Used at every request boundary to resolve the tenant; `host.split(":")[0]` strips any port.
- `active` — when `False`, the `org_active` pipeline step blocks all logins for this organisation.
- `body` / `help_info` — `RichTextField` values cleaned by `relaxed_clean_html`.
- `page_title` — defaults to `title` on first save if left blank.
- `providers` — reverse relation to `OAuth2Provider`, one row per configured login method. Use `get_provider(provider_id)` to fetch one.

`enabled_components()` yields `OrganisationComponent` instances where `enabled=True` and `is_valid` is truthy.

`Organisation` implements `RoleContextMixin` with `roles_cls = OrganisationRoles`, giving it `add_roles()`, `remove_roles()`, `get_roles()`, and `has_roles()` / `has_any_roles()` from the mixin.

Auditlog is registered on `title`, `body`, `page_title`, `host`, `active`, and `help_info` only.

### OrganisationRoles
One row per `(user, organisation)` pair. The `assigned` field is a `RolesField` (PostgreSQL `ArrayField`). Valid values are `org_manager` and `meeting_creator`.

The `context` FK is to `Organisation` and the `organisation` property returns `self.context` — this satisfies the `OrganisationContext` ABC without a duplicate column.

Changes fire `roles_added` / `roles_removed` core signals, which in turn publish WebSocket messages (see Signals below).

Auditlog stores `{"o": self.context_id}` in `get_additional_data()` for every change.

### OAuth2Provider
Holds the OAuth2/OIDC credentials used for SSO login. **Required foreign key** to `Organisation`, one row per social auth backend, uniquely constrained on `(organisation, provider_id)`. Fields: `provider_id` (the `social_core` backend `name`), `scope` (space-separated), `client_id`, `client_secret`, `oidc_endpoint` (blank unless an OIDC backend needs to override its own default issuer), `primary`, `hidden`.

Look one up with `organisation.get_provider(provider_id)`, which raises `OAuth2Provider.DoesNotExist`.

The `backend` property returns the backend class for `provider_id`, or `None` when it is not in `AUTHENTICATION_BACKENDS`. It is the single lookup point.

`OAuth2Provider.visible_for(organisation)` returns the login options to offer: `hidden` rows and rows with no enabled backend dropped, `primary` first, the rest by title lowercased. Sorting is in Python because the title comes from the backend class, not the row. `hidden` only affects this list — such a provider still logs in fine, which is what you want for something reached by a hint rather than a button.

### TermsOfService
A TOS document for an organisation. `required=True` means a user must consent before accessing the platform. Multiple TOS documents per organisation are supported; each is accepted independently via `UserConsent`.

### UserConsent
Records user acceptance of a `TermsOfService`. Unique per `(user, tos)`. `revoked` timestamp is non-null when consent has been withdrawn; check via `is_revoked` property. The `organisation` property traverses `self.tos.organisation`.

## Roles

Defined in `roles.py`:

| Constant | Name | String value |
|---|---|---|
| `ROLE_ORG_MANAGER` | Organisation manager | `org_manager` |
| `ROLE_MEETING_CREATOR` | Meeting creator | `meeting_creator` |

`is_meeting_creator` grants access for either `meeting_creator` or `org_manager` — org managers implicitly have meeting creation rights without needing the secondary role.

## Permissions (`rules.py`)

All permissions are guarded by predicates registered via the `rules` library:

| Permission | Predicate |
|---|---|
| `organisation.change` | `is_manager` |
| `organisation.manage` | `is_manager` |
| `organisation.change_roles` | `is_manager` |
| `organisation.view_roles` | `is_manager` |

There is no explicit `VIEW` permission on `Organisation` — the list endpoint is publicly readable (requires `IsAuthenticatedOrReadOnly` only).

## REST API

All ViewSets are registered to the central router in `rest_api/views.py`.

### `OrganisationViewSet` (`/api/organisation/`)
- `list` — returns the single organisation matching the request's `Host` header. Unauthenticated callers get the org by hostname lookup. Authenticated callers get their own org; if their org's host does not match the request host, a `401 AuthenticationFailed` is raised with the message "You're logged in to another organisation".
- `change` (`PATCH /api/organisation/change/`) — partial update of `body`, `help_info`, and `page_title`. Requires `org_manager`.
- Create/delete are not supported (405).

The serializer also exposes read-only computed fields: `providers` and `components` (enabled org components via `OrganisationComponentSerializer`).

`providers` is the list of login methods, from `OAuth2Provider.visible_for()`.

### `OrganisationRolesViewSet` (`/api/organisation-roles/`)
- `list` — returns all `OrganisationRoles` for the user's organisation. Non-managers see an empty list (queryset scoped by `view_roles` permission check).
- Supports `?user_id_in=1,2,3` filter and `^user__first_name` / `^user__last_name` search.
- `available` (`GET /api/organisation-roles/available/`) — lists valid role definitions; open to anonymous.
- `add_roles` (`POST /api/organisation-roles/add/`) — adds roles; requires `change_roles` on the caller's org. The `user` field is validated by `SameOrgUserField` to block cross-org assignments. Logs the change via `log_roles_change`.
- `remove_roles` (`POST /api/organisation-roles/remove/`) — removes roles; returns `204` if the row is deleted entirely after the last role is removed. Also logs.

### `MatchOrphansViewSet` (`/api/match-orphans/`)
ID-proxy service endpoint. Requires `HasIDProxyAPIKey`. Accepts `?email_in=a@b.com,c@d.com` (comma-separated, required). Returns users with no `identity_id` matching those emails, along with their organisation host. Used for pre-login orphan matching.

### `HandleIdentitiesViewSet` (`/api/handle-identities/`)
ID-proxy service endpoint. Requires `HasIDProxyAPIKey`. Accepts `?identity_in=uid1,uid2` (required). Provides a `query` action that returns user details for the matched identities. Raises `ValidationError` if >3 users would be affected, if any affected user has org roles / staff / superuser status, or if identities span multiple organisations. All validation errors are also emitted to the `notification_logger`.

## SSO Backends (`backends.py`)

`OrganisationBackendMixin` is the shared multi-tenant half of every social auth backend in the project. Mix it in **before** the `social_core` backend, so `get_scope()` can extend `DEFAULT_SCOPE` through `super()`. It provides:
- `organisation` — resolved from the request hostname.
- `provider` — that organisation's `OAuth2Provider` row for `self.name`; raises `AuthException` if there is none.
- `get_key_and_secret()` / `get_scope()` — credentials and the org's scopes merged with the backend's defaults.
- `get_identity_data(social)` — what this provider vouches for about a person, as
  `{scope: [value, ...]}`. The shape is the id proxy's, which got here first; every backend
  normalises into it on the way in (in `extra_data()`), so one lookup reads them all. The
  default reads `social.extra_data["user_data"]`, which is what `IDProxyOAuth2` already
  writes. Only **validated** data belongs here — it decides which invites a user matches and
  which email they may set. `utils.get_user_identity_data(user)` merges it across every
  enabled backend and across the accounts sharing a person's `identity_id`; callers are
  `UserSerializer.validate_email`, `/api/user/email_choices/` and
  `HandleMatchedInvitesViewSet`.
- `get_title()`, `get_login_url(provider)`, `get_profile_url(provider)`, `get_logout_url(provider)` — what the SPA shows, and where it sends people to log in, manage their account and log out. Backends set `TITLE`; the default login URL is `reverse("social:begin", args=[name])` and the other two default to `None`. They take the **provider row**, not the organisation, because an OIDC backend's URLs derive from its issuer — which is a per-provider column. They are classmethods, so they work outside a login request where there is no strategy.

`IDProxyOAuth2` is the backend for the project's central identity proxy service. Key behaviours:
- Overrides `get_login_url()`: the id proxy is entered through itself (`{ID_HOST}/login-to/{host}`), because it must know which tenant is asking before it can offer a login.
- Merges `OAuth2Provider.scope` with `DEFAULT_SCOPE = ["email", "identity"]` and sorts the combined list for deterministic OAuth requests.
- `AUTHORIZATION_URL`, `ACCESS_TOKEN_URL`, and `IDENTITY_URL` can be overridden per-environment via `SOCIAL_AUTH_IDPROXY_<KEY>` settings.
- `extra_data` restructures the flat `user_data` list from the identity server into `{scope: [data, ...]}` dicts before storage.

## Authentication Pipeline (`pipeline.py`)

Custom PSA pipeline steps used in `SOCIAL_AUTH_PIPELINE`:

- `org_active` — raises `AuthException` if `backend.organisation.active` is `False`.
- `social_user` — replaces PSA's built-in `social_user`. For `idproxy` it handles two problematic scenarios that cause infinite redirect loops:
  - A `UserSocialAuth` pointing to an inactive user: redirects the auth to the most-recently-active user sharing the same `identity_id`, transferring the social auth record in the process.
  - Identity-ID lookup with no social auth: only considers `is_active=True` users.

  Every other backend returns early, resolving by `(provider, uid)` alone. None of the above applies to them: `identity_id` is not their namespace.
- `create_user` — creates a new user scoped to `backend.organisation`, passing `identity_id=uid` **only for `idproxy`**; an account created by any other backend has no `identity_id` and is reached through its `UserSocialAuth`.
- `ensure_userid` — generates a slugified `userid` from first/last name if not already set. Deduplicates by appending a suffix.
- `inherit_users` — maintains `identity_id` for `idproxy` only: it overwrites when the uid has changed, and `extra_identity_ids` in the response updates all same-org active users carrying those IDs to share the authenticated user's `identity_id`. Returns immediately for every other backend — see "`identity_id` belongs to the id proxy" below.
- `bump_permissions` — if the identity server response includes `is_superuser: true`, grants `org_manager` role to the user.
- `remove_nonmatching_email` — syncs the user's `email` field against the identity server's email scope data. Clears email if the scope is not present, but only when `idproxy` is the provider.

## WebSocket Channel (`channels.py`)

`OrganisationChannel` is a `ContextChannel` keyed by `Organisation` pk. Has `permission = None` (no explicit subscribe permission; any authenticated user can subscribe).

The client never subscribes to it: the consumer does it on connect, for the organisation the user belongs to (`VoteitConsumer.subscribe_to_organisation`). The stream is the ordinary one, built inline rather than on a worker because the channel is small.

On subscribe, the `organisation.roles` collector pushes the user's current org roles as a `RolesChanged` message in the initial `channel.state` bundle. This is how the frontend learns its own role set on connection.

## Signals (`signals.py`)

- `setting_changed` → `reload_social_backends` — force-reloads social_core's backend cache when `AUTHENTICATION_BACKENDS` changes. `load_backends()` caches in a module-global `BACKENDSCACHE` and **ignores its argument once warm**, so without this, `override_settings(AUTHENTICATION_BACKENDS=...)` is a silent no-op and `OAuth2Provider.backend` answers from stale data. Only fires under test overrides; in production the setting never changes.
- `Organisation post_save` (not created) — publishes `OrganisationChanged` to `OrganisationChannel`. Skipped on `raw` saves.
- `organisation.roles` collector on `OrganisationChannel` — the subscribing user's roles.
- `roles_added` on `OrganisationRoles` — publishes `RolesChanged` to both `OrganisationChannel` and the affected user's personal `UserChannel`. Skipped on `raw` saves.
- `roles_removed` on `OrganisationRoles` — same dual-publish for `RolesRemoved`. Not guarded by `@disable_on_raw_save` (intentional asymmetry).
- `User post_save` / `pre_delete` (in `voteit.core.signals`) — publishes `InvalidateUserCache` to the user's own organisation channel.

## WebSocket Messages (`messages.py`)

- `OrganisationChanged` (`organisation.changed`) — outgoing; payload is the full `OrganisationSerializer` output.

## Scheduled Jobs (`jobs.py`)

- `cleanup_extra_data_for_older_users` (daily at 04:00) — clears `UserSocialAuth.extra_data` for records not modified in the past 365 days. Prevents long-lived accumulation of potentially sensitive identity data. The credential row itself survives — it is still how its owner reaches the account it belongs to.

## Non-obvious design decisions

**`identity_id` belongs to the id proxy, and to nothing else.** It holds an id proxy
identifier, so no other provider may write one there and no other provider's uid may be
looked up in it — the values would be two unrelated namespaces sharing a column. Only
`idproxy` gets an `identity_id` from `create_user`, only `inherit_users` under `idproxy`
maintains it, and the identity lookups in `social_user` are skipped entirely for every
other backend, which resolve by `UserSocialAuth` alone the way stock PSA does.

Within the id proxy it is the **person**: one human may hold several accounts, and
`identity_id` is what groups them — `UserView.get_queryset` / `alternate` / `switch`,
`UserMerger._validate` and the admin `LinkedFilter` duplicate view all read it.

Two consequences of an account that has no `identity_id` (anyone who only ever logged in
with another provider):

- It has no alternates and cannot `switch`, which is correct — nothing has established that
  any other row is the same person.
- `UserView.get_queryset` unions `pk=request.user.pk` with the identity group, so such a
  user can still read and edit their own row.

Matching one of those logins to an existing account is a separate job, done on evidence that
can actually be checked (a verified email and name, or the user proving they hold both
credentials) — never by reading a uid as though it were an identity.

**Tenant resolution via `Host` header, not URL prefix.** The `OrganisationViewSet.get_object()` method (and `IDProxyOAuth2.organisation`) both strip the port from `request.get_host()` and look up `Organisation` by `host`. There is no pk in the URL. This means every request implicitly scopes to exactly one tenant without any URL changes — but it also means cross-tenant operations in tests must use `SERVER_NAME` / `HTTP_HOST` overrides.

**`OrganisationViewSet.list` returns one item, not a list.** The endpoint name follows REST convention (`-list`) but the view returns a single object. This is intentional: the SPA always fetches "its" organisation, and having a list endpoint avoids a custom action name.

**`social_user` pipeline step replaces PSA's built-in.** The built-in would return an inactive user when a `UserSocialAuth` points to one, causing PSA's `do_complete` to reject every login attempt in a persistent loop. The custom step detects inactive users and redirects auth to an active duplicate (by `identity_id`) within the same organisation. This is `idproxy`-only; other backends take the early return described above.

**Subscribed on connect, not on request.** A user belongs to exactly one organisation, so a `channel.subscribe` for it would only ever have one right answer. The consumer subscribes for them and sends the state straight away, which also makes the organisation channel the natural home for anything addressed to "every socket of this tenant" — `InvalidateUserCache` used to go to a global `online` group instead.

**Role push on channel subscribe, not on login.** Org roles are not embedded in the login response. They are pushed as a `RolesChanged` message when the frontend subscribes to `OrganisationChannel`. This keeps the auth flow simple and the WS channel as the single source of truth for role state.

**`bump_permissions` grants `org_manager` when identity server returns `is_superuser`.** This is not Django's `is_superuser` flag — it is a claim from the identity server. It grants an org-scoped manager role, not platform superuser access.

**One `OAuth2Provider` per backend, not per organisation.**

**`UserConsent` / `TermsOfService` models exist but have no active REST endpoints.** The ViewSets and serializers are commented out. They will be used later.
## Tests

```
python manage.py test voteit.organisation --keepdb --failfast
```

`testing.py` holds `DummyOAuth2`, a second social auth backend, and
`dummy_backend_enabled()`, an `override_settings` that adds it to
`AUTHENTICATION_BACKENDS`. Multi-provider behaviour is tested against that rather than
against a real second backend.

The override only bites because of the `setting_changed` receiver above.

Test modules:
- `tests/test_models.py` — model and `OAuth2Provider` basics.
- `tests/test_rules.py` — predicate logic for `is_manager` and `is_meeting_creator`.
- `tests/test_backends.py` — `IDProxyOAuth2` scope merging.
- `tests/test_pipeline.py` — pipeline steps: `ensure_userid`, `social_user` inactive-user handling, `inherit_users` identity ownership, social auth transfer.
- `tests/test_signals.py` — WS publish on org save, role changes, and channel subscribe.
- `tests/test_jobs.py` — `cleanup_extra_data_for_older_users`.
- `tests/test_utils.py` — `get_user_identity_data` across duplicate users, providers and disabled backends.
- `tests/test_auditlog.py` — auditlog field coverage.
- `tests/test_docs.py` — runs module doctests (`backends.py` docstrings).
- `rest_api/tests/test_views.py` — `OrganisationViewSet`, `OrganisationRolesViewSet`, `MatchOrphansViewSet`, `HandleIdentitiesViewSet`.
- `rest_api/tests/test_python_social_integration.py` — end-to-end SSO login flows using `responses` mock library.
