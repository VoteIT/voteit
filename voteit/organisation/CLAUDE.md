# voteit.organisation

Manages the top-level tenant (`Organisation`) and everything directly owned by it: org-level role assignments, terms of service, OAuth2/SSO configuration, and the identity proxy integration (Python Social Auth). Every user and every meeting in the system belongs to exactly one organisation. The app also owns the `IDProxyOAuth2` PSA backend and the full authentication pipeline that maps external identities to local users.

## Models

### Organisation
The root tenant. Key fields:
- `host` — unique hostname (e.g. `"meeting.myorg.se"`). Used at every request boundary to resolve the tenant; `host.split(":")[0]` strips any port.
- `active` — when `False`, the `org_active` pipeline step blocks all logins for this organisation.
- `body` / `help_info` — `RichTextField` values cleaned by `relaxed_clean_html`.
- `page_title` — defaults to `title` on first save if left blank.
- `provider` — one-to-one reverse relation to `OAuth2Provider`; raises `ObjectDoesNotExist` if no SSO is configured.

`enabled_components()` yields `OrganisationComponent` instances where `enabled=True` and `is_valid` is truthy.

`Organisation` implements `RoleContextMixin` with `roles_cls = OrganisationRoles`, giving it `add_roles()`, `remove_roles()`, `get_roles()`, and `has_roles()` / `has_any_roles()` from the mixin.

Auditlog is registered on `title`, `body`, `page_title`, `host`, `active`, and `help_info` only.

### OrganisationRoles
One row per `(user, organisation)` pair. The `assigned` field is a `RolesField` (PostgreSQL `ArrayField`). Valid values are `org_manager` and `meeting_creator`.

The `context` FK is to `Organisation` and the `organisation` property returns `self.context` — this satisfies the `OrganisationContext` ABC without a duplicate column.

Changes fire `roles_added` / `roles_removed` core signals, which in turn publish WebSocket messages (see Signals below).

Auditlog stores `{"o": self.context_id}` in `get_additional_data()` for every change.

### OAuth2Provider
Holds the OAuth2 credentials used for SSO login. One-to-one with `Organisation` (nullable — an org can exist without one). Fields: `scope` (space-separated), `client_id`, `client_secret`. The `id_backend_host` property prefers the `ID_HOST_BACKEND` setting over `ID_HOST` (dev override for container networking).

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

The serializer also exposes read-only computed fields: `login_url` (the IDProxy login entry point), `id_host` (from settings), `scope` (space-split list from `OAuth2Provider`), and `components` (enabled org components via `OrganisationComponentSerializer`).

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

## SSO Backend (`backends.py`)

`IDProxyOAuth2` is a `python-social-auth` backend for the project's central identity proxy service. Key behaviours:
- Resolves the `Organisation` from the request hostname (cached via `@cached_property`).
- Retrieves `client_id` / `client_secret` from `Organisation.provider` rather than settings.
- Merges `OAuth2Provider.scope` with `DEFAULT_SCOPE = ["email", "identity"]` and sorts the combined list for deterministic OAuth requests.
- `AUTHORIZATION_URL`, `ACCESS_TOKEN_URL`, and `IDENTITY_URL` can be overridden per-environment via `SOCIAL_AUTH_IDPROXY_<KEY>` settings.
- `extra_data` restructures the flat `user_data` list from the identity server into `{scope: [data, ...]}` dicts before storage.

The `IDPROXY_PROVIDER` constant (`"idproxy"`) is exported from `__init__.py`.

## Authentication Pipeline (`pipeline.py`)

Custom PSA pipeline steps used in `SOCIAL_AUTH_PIPELINE`:

- `org_active` — raises `AuthException` if `backend.organisation.active` is `False`.
- `social_user` — replaces PSA's built-in `social_user`. Handles two problematic scenarios that cause infinite redirect loops:
  - A `UserSocialAuth` pointing to an inactive user: redirects the auth to the most-recently-active user sharing the same `identity_id`, transferring the social auth record in the process.
  - Identity-ID lookup with no social auth: only considers `is_active=True` users.
- `create_user` — creates a new user scoped to `backend.organisation`, passing `identity_id=uid`.
- `ensure_userid` — generates a slugified `userid` from first/last name if not already set. Deduplicates by appending a suffix.
- `inherit_users` — if the identity server returns `extra_identity_ids`, updates all same-org active users carrying those IDs to share the authenticated user's `identity_id`.
- `bump_permissions` — if the identity server response includes `is_superuser: true`, grants `org_manager` role to the user.
- `remove_nonmatching_email` — syncs the user's `email` field against the identity server's email scope data. Clears email if the scope is not present.

## WebSocket Channel (`channels.py`)

`OrganisationChannel` is a `ContextChannel` keyed by `Organisation` pk. Has `permission = None` (no explicit subscribe permission; any authenticated user can subscribe).

On subscribe, `organisation_channel_subscribed` pushes the user's current org roles as a `RolesChanged` message appended to the initial app state. This is how the frontend learns its own role set on connection.

## Signals (`signals.py`)

- `Organisation post_save` (not created) — publishes `OrganisationChanged` to `OrganisationChannel`. Skipped on `raw` saves.
- `channel_subscribed` on `OrganisationChannel` — pushes the subscribing user's roles in the initial app state.
- `roles_added` on `OrganisationRoles` — publishes `RolesChanged` to both `OrganisationChannel` and the affected user's personal `UserChannel`. Skipped on `raw` saves.
- `roles_removed` on `OrganisationRoles` — same dual-publish for `RolesRemoved`. Not guarded by `@disable_on_raw_save` (intentional asymmetry).

## WebSocket Messages (`messages.py`)

- `OrganisationChanged` (`organisation.changed`) — outgoing; payload is the full `OrganisationSerializer` output.

## Scheduled Jobs (`jobs.py`)

- `cleanup_extra_data_for_older_users` (daily at 04:00) — clears `UserSocialAuth.extra_data` for records not modified in the past 365 days. Prevents long-lived accumulation of potentially sensitive identity data.

## Non-obvious design decisions

**Tenant resolution via `Host` header, not URL prefix.** The `OrganisationViewSet.get_object()` method (and `IDProxyOAuth2.organisation`) both strip the port from `request.get_host()` and look up `Organisation` by `host`. There is no pk in the URL. This means every request implicitly scopes to exactly one tenant without any URL changes — but it also means cross-tenant operations in tests must use `SERVER_NAME` / `HTTP_HOST` overrides.

**`OrganisationViewSet.list` returns one item, not a list.** The endpoint name follows REST convention (`-list`) but the view returns a single object. This is intentional: the SPA always fetches "its" organisation, and having a list endpoint avoids a custom action name.

**`social_user` pipeline step replaces PSA's built-in.** The built-in would return an inactive user when a `UserSocialAuth` points to one, causing PSA's `do_complete` to reject every login attempt in a persistent loop. The custom step detects inactive users and redirects auth to an active duplicate (by `identity_id`) within the same organisation.

**Role push on channel subscribe, not on login.** Org roles are not embedded in the login response. They are pushed as a `RolesChanged` message when the frontend subscribes to `OrganisationChannel`. This keeps the auth flow simple and the WS channel as the single source of truth for role state.

**`bump_permissions` grants `org_manager` when identity server returns `is_superuser`.** This is not Django's `is_superuser` flag — it is a claim from the identity server. It grants an org-scoped manager role, not platform superuser access.

**`UserConsent` / `TermsOfService` models exist but have no active REST endpoints.** The ViewSets and serializers are commented out. The models remain for potential future use and because historic data may exist.

## Tests

```
python manage.py test voteit.organisation --keepdb --failfast
```

Test modules:
- `tests/test_models.py` — model and `OAuth2Provider` basics.
- `tests/test_rules.py` — predicate logic for `is_manager` and `is_meeting_creator`.
- `tests/test_backends.py` — `IDProxyOAuth2` scope merging.
- `tests/test_pipeline.py` — pipeline steps: `ensure_userid`, `social_user` inactive-user handling, social auth transfer.
- `tests/test_signals.py` — WS publish on org save, role changes, and channel subscribe.
- `tests/test_jobs.py` — `cleanup_extra_data_for_older_users`.
- `tests/test_utils.py` — `get_idproxy_user_data` across duplicate users.
- `tests/test_auditlog.py` — auditlog field coverage.
- `tests/test_docs.py` — runs module doctests (`backends.py` docstrings).
- `rest_api/tests/test_views.py` — `OrganisationViewSet`, `OrganisationRolesViewSet`, `MatchOrphansViewSet`, `HandleIdentitiesViewSet`.
- `rest_api/tests/test_python_social_integration.py` — end-to-end SSO login flows using `responses` mock library.
