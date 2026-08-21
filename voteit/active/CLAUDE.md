# voteit.active

Tracks which participants have marked themselves as active in a meeting. "Active" is a voluntary presence signal — distinct from WebSocket connection presence — that lets other participants see who intends to participate. The feature is opt-in per meeting via `ActiveUsersComponent`.

## Model

**`ActiveUser`** — a join table: `(meeting, user)` unique pair with a `created` timestamp. No state machine; records are simply created or deleted. Accessed as `meeting.active_users`.

## Component gate

The entire feature is controlled by `ActiveUsersComponent` (registered in `meeting_components`). When the component is disabled, the REST queryset returns no meetings (404 for all endpoints) and `ActiveUsers` messages are not pushed on channel subscribe. `disable_on_close = True` so the component auto-disables when the meeting closes.

Check whether the feature is enabled: `active_enabled_for_meeting(meeting)` in `utils.py`.

## REST API

`ActiveUserViewSet` registered at `active-users/`. The queryset returns **meetings** (not `ActiveUser` records) scoped to meetings where:
- the requesting user is a participant, and
- `ActiveUsersComponent` is enabled.

| Action | Method | URL | Notes |
|---|---|---|---|
| `list` | GET | `active-users/` | Always returns `[]`; data comes via WebSocket |
| `retrieve` | GET | `active-users/{id}/` | Returns `{title, id}` for the meeting |
| `active` | POST | `active-users/{id}/active/` | Body: `{"active": true/false}`; creates or deletes the `ActiveUser` row |
| `purge` | POST | `active-users/{id}/purge/` | Moderator-only; removes stale active users |

**`active` action responses:**
- `active=true`, record created → `201 Created`
- `active=true`, record already exists → `200 OK` (idempotent)
- `active=false` → `204 No Content` (idempotent — no error if no record)

**`purge` action:**
Body: `{"hours": 1}` (default 1, range 0–72). Removes `ActiveUser` records where the user has no `Connection` with `last_action` within the given hours. `hours=0` uses a 5-minute cutoff (not zero) to avoid accidentally purging users who are actively connected right now.

## Permissions

| Permission | Guard |
|---|---|
| `active_user.change` | `is_participant & meeting_upcoming_ongoing & users_active_component_enabled` |
| `active_user.view` | `is_participant` |

`purge` maps to `PERM.CHANGE`; `active` has no permission class (access controlled entirely by the queryset).

## WebSocket messages (`messages.py`)

Both are outgoing-only, published to `MeetingChannel`:

- **`active_user.all`** (`ActiveUsers`) — full list of active user PKs for a meeting. Pushed on channel subscribe and when the component is enabled.
- **`active_user.changed`** (`ActiveUserChanged`) — delta: `{meeting, user, active: bool}`. Pushed on `ActiveUser` creation (`active=true`) and deletion (`active=false`).

## Signals (`signals.py`)

- `active.users` collector on `MeetingChannel` → pushes `ActiveUsers`. `applicable()`
  returns False when the component is off, so the section is never even announced.
- `post_save` on `MeetingComponent` → when `ActiveUsersComponent` is enabled, immediately pushes the current `ActiveUsers` list.
- `post_save` on `ActiveUser` (created only) → publishes `ActiveUserChanged(active=True)` synchronously.
- `pre_delete` on `ActiveUser` → publishes `ActiveUserChanged(active=False)` deferred to transaction commit.
- `pre_delete` on `MeetingRoles` → deletes the user's `ActiveUser` record for that meeting, so leaving a meeting auto-clears active status.

## Testing

```bash
python manage.py test voteit.active --keepdb --failfast
```

Tests: `tests/test_models.py` (unique constraint), `tests/test_rules.py` (permissions), `tests/test_signals.py` (WS message assertions), `rest_api/tests/test_views.py` (full endpoint coverage including purge edge cases).
