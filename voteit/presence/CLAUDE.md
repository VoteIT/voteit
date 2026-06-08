# voteit/presence

This package is no longer used, replaced by voteit.active!

The presence app provides an attendance-check mechanism for meetings. A moderator opens a `PresenceCheck`, participants register themselves as present (creating `Presence` records), and the moderator closes it. The closed check is then used as the source of truth when building an electoral register for polls — only users who were both present and hold the `potential_voter` role become eligible voters.

## Models

**`PresenceCheck`** — a single attendance-check session tied to a `Meeting`. Key fields:
- `state`: plain `CharField` (no choices enforced at the model level; `editable=False`). Managed externally; the migration history shows it moved from FSM-managed choices `open`/`closed` to a free-form field as part of the PySM migration.
- `present_users`: M2M through `Presence`; convenience accessor for the set of attending users.
- `opened` / `closed`: timestamps set at creation and when closed.
- `present_user_pks()`: returns a list of `(user_id,)` tuples for all attending users.

Multiple `PresenceCheck` objects can exist per meeting (one per roll-call session).

**`Presence`** — the through table for `PresenceCheck.present_users`. Enforces a DB unique constraint on `(user, presence_check)` so a user can only be registered once per check. `user` uses `on_delete=RESTRICT` to prevent accidentally deleting users who appear in historical records. The `created` timestamp records when the user was marked present.

`Presence` inherits `MeetingContext` but does not store a direct `meeting` FK — it resolves `.meeting` via `self.presence_check.meeting`.

## Component gate

The feature is opt-in per meeting via `PresenceCheckComponent` (registered in `meeting_components`). `disable_on_close = True` so the component auto-disables when the meeting closes. Check enablement with `meeting.component_enabled("presence_check")`.

The `presence_component_active` predicate in `rules.py` uses this gate but is currently unused by any registered permission rule.

## Permissions

Defined in `rules.py` for `PresenceCheck` only. `Presence` records have no rules registered — access is controlled entirely through the check.

| Permission | Guard |
|---|---|
| `presence_check.add` | `always_deny` — creation is forbidden via the rules API |
| `presence_check.delete` | `is_moderator` |
| `presence_check.view` | `is_participant` |

`PresenceCheck` creation in practice goes through code paths that bypass the `add` permission (e.g. admin or direct ORM calls), not through a guarded REST action.

## How other apps use it

The only external consumer is `voteit.poll`. `PresenceCheckPolicy` (`voteit/poll/app/er_policies/presence_check.py`) is an `ElectoralRegisterPolicy` that accepts a `presence_check` keyword argument in `get_voters()`. It intersects `presence_check.present_users` with the set of users holding `ROLE_POTENTIAL_VOTER`, then produces a `{user_pk: weight}` dict. If group votes are active on the meeting, weights are distributed equally via `calc_group_votes_equal`.

`Meeting` carries a type annotation `presence_checks: PresenceCheck.Manager` (reverse FK, added via `related_name="presence_checks"`) but no logic in the meeting model itself.

## Notable design decisions

- **Historic app** - no longer used
- **`Presence` is intentionally immutable after creation.** The model docstring explicitly notes there is no update use case — updating a presence record would constitute tampering. Only create and delete are meaningful operations.

## Tests

There are no test files in this app. Run:

```bash
python manage.py test voteit.presence --keepdb --failfast
```
