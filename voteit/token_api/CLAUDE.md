# token_api

The `token_api` app provides long-lived meeting-scoped API keys that let external
services (integrations, bots, import scripts) interact with VoteIT resources without
a human session. Each key is bound to a single meeting and carries an explicit list
of permission scopes. It is distinct from the session/token auth used by the regular
DRF API: there are no user credentials involved — only the raw key and its scopes.

## Model

### `MeetingAPIKey`

Extends `AbstractAPIKey` from `djangorestframework-api-key`. The underlying library
handles key hashing and prefix storage; VoteIT adds:

- `meeting` — FK to `Meeting` (CASCADE). Keys are strictly scoped to one meeting.
- `user` — FK to a dedicated inactive system user created at key-issuance time (see
  below). Used as the auditlog actor for all writes made via this key.
- `scopes` — `JSONField` (list of strings). Validated on save by
  `validate_api_key_scopes`; redundant specific scopes are normalised away by
  `normalize_scopes` (e.g. `["invites.*", "invites.list"]` → `["invites.*"]`).
- `last_used` — `DateTimeField`, updated at most once per minute to reduce write
  pressure (throttled by `LAST_USED_UPDATE_THRESHOLD = timedelta(minutes=1)`).
- Keys expire 120 days after creation (set in the create view).

### `create_api_key_user(meeting)`

Creates a dedicated inactive `User` (`username="apikey-<uuid>"`, `is_active=False`,
unusable password) belonging to the same organisation as the meeting. One such user
is created per key (including each cycle). This ensures every auditlog entry carries
a stable, attributable actor even though no real person authenticated.

## Permissions (`rules.py`)

These govern who can manage keys themselves (via the main DRF API), not what the keys
can access.

| Permission      | Predicate                              |
|-----------------|----------------------------------------|
| `VIEW`          | `is_moderator`                         |
| `ADD`           | `is_moderator & meeting_upcoming_ongoing` |
| `CHANGE`        | `is_moderator & meeting_upcoming_ongoing` |
| `DELETE`        | `is_moderator` (effectively: revoke)   |

Creating and cycling keys is blocked once a meeting is closed; revoking is always
allowed.

## Authentication and scope enforcement (`auth.py`)

### `MeetingAPIKeyAuthentication`

A DRF `BaseAuthentication` subclass. It reads the key from the `Authorization: Api-Key
<key>` header, looks it up via `MeetingAPIKey.objects.get_from_key()`, and:

1. Raises `AuthenticationFailed` if the key does not exist or has expired.
2. Attaches the resolved `MeetingAPIKey` object to `request.meeting_api_key`.
3. Returns `(key.user, None)` — the inactive system user becomes `request.user` for
   the duration of the request.

`get_usable_keys()` in `MeetingAPIKeyManager` always selects-related `user`,
`meeting`, and `meeting.organisation` to avoid N+1 queries during authentication.

### `MeetingAPIKeyScope`

A DRF `BasePermission` applied on all token-API views.

- **`has_permission`**: Looks up `view.token_api_scope` (falls back to
  `view.basename`) and `view.action`, then checks that at least one scope in
  `key.scopes` matches via `_scope_matches(scope, resource, action)`. Scope format is
  `resource.action` or `resource.*`. If no key is present but the user is
  session-authenticated, read-only actions (`list`, `retrieve`, `metadata`) pass — but
  `get_queryset` returns an empty queryset so no data is exposed.
- **`has_object_permission`**: Ensures the retrieved object belongs to the same
  meeting as the key (compares `key.meeting_id` with `obj.meeting_id` or
  `obj.meeting`).

## Token-API router and base viewset (`__init__.py`, `base.py`)

The app has its own `DefaultRouter` (separate from the main DRF router at
`voteit/core/rest_api/router.py`). It is mounted at `token-api/` in `project/urls.py`
under the namespace `token-api`.

All token-API viewsets must inherit from `MeetingApiBaseViewSet`. Use the
`@register_meeting_api(prefix)` decorator to register a viewset; it asserts the
inheritance requirement and registers with the token-API router.

`MeetingApiBaseViewSet` sets:
- `authentication_classes = [MeetingAPIKeyAuthentication, SessionAuthentication]`
- `permission_classes = [MeetingAPIKeyScope]`
- `throttle_classes = [TokenAPIUserThrottle, TokenAPIAnonThrottle]` — rates
  configured in settings as `token_api_user: 60/min`, `token_api_anon: 1/sec`.
- `get_queryset()` returns `.none()` when no API key is present on the request.
- `initial()` patches the auditlog context actor after DRF authentication has run
  (see "Non-obvious design decisions" below).

## Scope validation (`validators.py`)

`_valid_scopes_map()` introspects the token-API router's registered viewsets at
runtime to build the set of valid `{resource: {actions}}`. Standard DRF actions plus
all `@action`-decorated methods are included. This means scopes are always in sync
with the actual views — no separate registry to maintain.

`validate_api_key_scopes` is attached as a `JSONField` validator on `MeetingAPIKey`
and is also called at the model level on every `save()`.

## Key management REST API (`api.py`)

Registered on the **main** DRF router (not the token-API router) at
`/api/meeting-api-token/`. Requires session auth as a meeting moderator.

| Action     | Method         | Description                                          |
|------------|----------------|------------------------------------------------------|
| `list`     | GET            | All keys for a meeting (`?meeting=<id>`)             |
| `retrieve` | GET `/{prefix}/` | Single key (never exposes the secret)              |
| `create`   | POST           | Issue a new key; returns `key` field once only       |
| `destroy`  | DELETE `/{prefix}/` | Revoke (sets `revoked=True`, does not delete)  |
| `cycle`    | POST `/{prefix}/cycle/` | Replace key atomically; deletes old record |
| `scopes`   | GET `/scopes/` | All valid scope strings; no auth required            |

Lookup is by `prefix` (not PK). `cycle` creates a fresh key with a new API user and
hard-deletes the old record (unlike `destroy` which only revokes).

`MeetingApiTokenViewSet` uses `VerboseAutoPermissionViewSetMixin`. The `create`
permission is set to `None` in `permission_type_map` because the meeting FK in the
serializer is validated via `validate_model_add`, which checks `ADD` permission
against the meeting object inline.

## Token-API resource views (`views/`)

Views registered on the token-API router (mounted at `token-api/`).

### `MeetingView` (`views/meeting.py`)

`GET /token-api/meeting/` — returns the single `Meeting` associated with the key,
serialized with `MeetingDetailSerializer`. Always responds with a single object (not
a list), or `[]` for session-authenticated requests. Required scope: `meeting.list`
or `meeting.*`.

### `InvitesView` (`views/invites.py`)

`/token-api/invites/` — full CRUD on `MeetingInvite` objects limited to the key's
meeting. The `meeting` field is removed from the create serializer
(`InviteCreateViaTokenSerializer`) and injected from the API key to prevent meeting
injection attacks. Supports `dryrun=true` (validates and returns result without
persisting).

## Non-obvious design decisions

**Auditlog actor patching.** Django's `AuditlogMiddleware` captures `request.user`
before DRF's authentication runs, so the actor is initially `None` or anonymous.
`MeetingApiBaseViewSet.initial()` mutates the existing auditlog context dict in-place
(via `auditlog_value.get()["actor"] = request.user`) after DRF has resolved the real
(system) user. This is intentional: it avoids re-setting up signals while still
attributing writes to the correct API key user.

**Inactive system user per key.** Each key gets a dedicated inactive user rather than
sharing one per meeting or using the moderator. This makes auditlog entries
unambiguous and avoids permission escalation — the system user carries no meeting
roles.

**Scope validation is router-derived.** `_valid_scopes_map()` calls
`router.registry` at runtime. It must not be called at module import time (circular
imports); it is called lazily inside validators and admin. This is why it is a
function, not a module-level constant.

**`last_used` throttled writes.** To avoid a database write on every authenticated
request, `last_used` is updated only when it is unset or more than 1 minute old.
The update uses `QuerySet.update()` (not `save()`) to skip signal overhead.

**Revoke vs. cycle vs. delete.** `destroy` sets `revoked=True` and keeps the
database record (for audit history). `cycle` hard-deletes the old record and issues a
fresh key — appropriate when a key has been compromised and the operator wants to
rotate credentials with zero gap.

**Session auth is intentionally allowed but restricted.** `SessionAuthentication` is
listed alongside `MeetingAPIKeyAuthentication` so that session-authenticated users
(e.g. browsing the API in development) can reach `list`/`retrieve` endpoints without
a 401. However, `MeetingAPIKeyScope.has_permission` returns `True` only for read-only
actions, and `get_queryset` always returns `.none()` for session requests, so no data
leaks.

## Tests

```
python manage.py test voteit.token_api --keepdb --failfast
```

Tests are split across `tests/` (unit tests for auth, validators, and the key
management viewset) and `views/tests/` (integration tests for each token-API
resource view). `test_docs.py` runs `README.md` as a doctest suite.
