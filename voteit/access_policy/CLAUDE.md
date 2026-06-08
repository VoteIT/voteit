# access_policy

Manages how users gain access to meetings. Provides an abstract `AccessPolicy` base model and a concrete `AutomaticAccess` implementation that immediately grants configurable meeting roles to any authenticated user who requests entry. The app also defines a registry so additional policy types can be plugged in without changes to the core.

## Tests

```bash
python manage.py test voteit.access_policy --keepdb --failfast
```

## Key files

- `models.py` — abstract `AccessPolicy` base class (`MeetingContext` + `RulesModelMixin`)
- `registries.py` — `access_policies`: `Registry(AccessPolicy)` for pluggable policy types
- `utils.py` — `get_policies(meeting, only_active=True)`: iterates the registry and returns policy instances for a given meeting
- `rules.py` — django-rules permissions for `AutomaticAccess` (ADD / CHANGE / DELETE)
- `app/policies/automatic.py` — `AutomaticAccess`: the only currently active policy implementation
- `rest_api/views.py` — `AccessPoliciesViewSet` (read-only, per meeting) and `AutomaticAccessViewSet` (full CRUD + `join` action)
- `rest_api/serializers.py` — `AutomaticAccessSerializer`, `CreateAutomaticAccessSerializer`, `MeetingAccessPoliciesSerializer`

## Models

### `AccessPolicy` (abstract)

Base class for all access policies. Lives in `models.py`.

| Field     | Type                  | Notes                                                   |
|-----------|-----------------------|---------------------------------------------------------|
| `active`  | `BooleanField`        | Policy is only applied when `True`                      |
| `meeting` | `OneToOneField`       | Related name uses `%(app_label)s_%(class)s` pattern    |

Required abstract properties: `name` (used as the registry key / identifier) and `title` (human-readable label).

### `AutomaticAccess`

Concrete policy in `app/policies/automatic.py`. Registered in `access_policies` via `@access_policies` decorator.

| Field         | Type         | Notes                                                                     |
|---------------|--------------|---------------------------------------------------------------------------|
| `roles_given` | `RolesField` | Which meeting roles are granted on join; validated against `MeetingRoles` |

`assign(user)` calls `meeting.add_roles(user, *self.roles_given)`. It is a no-op if `roles_given` is empty.

Registered with `django-auditlog`; `id` is excluded from audit log entries so only meaningful field changes are recorded.

## Permissions (`rules.py`)

All `AutomaticAccess` permissions require the meeting to not be archived, and the user to be a meeting moderator.

| Permission                         | Predicate                              |
|------------------------------------|----------------------------------------|
| `AutomaticAccess.get_perm(ADD)`    | `meeting_not_archived & is_moderator`  |
| `AutomaticAccess.get_perm(CHANGE)` | `meeting_not_archived & is_moderator`  |
| `AutomaticAccess.get_perm(DELETE)` | `meeting_not_archived & is_moderator`  |

`get_perm` comes from `RulesModelMixin` (the `rules` library); it generates permission strings of the form `"access_policy.add_automaticaccess"` etc. The ADD check takes the `Meeting` as its object; CHANGE and DELETE take the `AutomaticAccess` instance.

There is no explicit VIEW permission — `retrieve`, `list`, and `join` bypass `VerboseAutoPermissionViewSetMixin` (mapped to `None`).

## REST API

### `AccessPoliciesViewSet`

`GET /api/access-policies/` — read-only. Returns meetings the request user belongs to, each serialized with their associated policies (active or inactive) via `MeetingAccessPoliciesSerializer`. Requires authentication.

`get_queryset` uses `Meeting.objects.for_user(request.user)` to scope to the user's meetings.

### `AutomaticAccessViewSet`

Base URL: `/api/access-policy-automatic/`

| Method / Action    | URL                               | Notes                                                                 |
|--------------------|-----------------------------------|-----------------------------------------------------------------------|
| `GET` list         | `/api/access-policy-automatic/`   | Scoped to policies in meetings of the user's organisation             |
| `GET` retrieve     | `/api/access-policy-automatic/{pk}/` | Scoped to meetings where user is moderator                        |
| `POST` create      | `/api/access-policy-automatic/`   | Permission checked in `validate_meeting` via `validate_model_add`     |
| `PATCH/PUT` update | `/api/access-policy-automatic/{pk}/` | Requires CHANGE permission; `meeting` field is read-only after create |
| `DELETE` destroy   | `/api/access-policy-automatic/{pk}/` | Requires DELETE permission                                        |
| `POST` join        | `/api/access-policy-automatic/{pk}/join/` | Open to any authenticated user; grants roles immediately      |

The `join` action validates that `aa.active` is `True` (returns HTTP 400 otherwise) and wraps `aa.assign(user)` in a durable `transaction.atomic`.

`get_queryset` uses two different filters depending on the action: `list`/`join` filter by the user's organisation (allowing any org member to see/join); all other actions filter to meetings where the user is a moderator.

## Registry

`access_policies = Registry(AccessPolicy)` in `registries.py`. Decorate a concrete subclass with `@access_policies` to register it under its `name` attribute. `get_policies(meeting)` in `utils.py` iterates all registered classes and fetches the corresponding DB instance for the given meeting.

## Non-obvious design decisions

### One policy instance per meeting per type
`AccessPolicy` uses `OneToOneField` to `Meeting`, so each policy type can only exist once per meeting. Creating via the API enforces the ADD permission on the `Meeting` object itself (not the policy instance), done in `CreateAutomaticAccessSerializer.validate_meeting` using the shared `validate_model_add` helper.

### `retrieve` and `list` have split querysets
The `get_queryset` split is intentional: for `join`, any authenticated user in the organisation must be able to look up the policy object even if they are not a moderator, so the queryset widens. For management actions, only the moderator's own meetings are exposed.

### `ModeratorApprovedAccess` was removed
The initial migration (0001) created `ModeratorApprovedAccess` and `AccessRequest` models. Both were deleted in migration 0007 (November 2023) along with `MeetingInvite` and `InviteDispatch`. Commented-out code and commented-out serializer entries in `serializers.py` are remnants of this.

### `RolesField` stores short codes
`roles_given` migrated from verbose role names (`"participant"`) to short codes (`"pa"`) in migration 0007. The `RolesField` now validates against `MeetingRoles.valid_roles.values()`.

### Auditlog excludes `id`
`AutomaticAccess` is registered with `exclude_fields=["id"]` so the auditlog records only `active`, `meeting`, and `roles_given` changes, keeping the log entries clean.
