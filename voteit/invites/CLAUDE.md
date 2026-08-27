# voteit/invites

Handles meeting invitations: creating them, matching identity data to users, accepting/rejecting, and applying secondary effects (group membership) when accepted.

## Core concepts

**`MeetingInvite`** — the central model. Belongs to a `Meeting`. Key fields:
- `user_data` — JSON dict of identity key/value pairs, e.g. `{"email": "jane@example.com"}` or `{"email": "...", "swedish_ssn": "..."}`. Validated to only contain string values. Unique per meeting.
- `roles` — roles to grant on accept (sorted, stored as ArrayField).
- `state` — plain `CharField` managed by `InviteStateMachine`. Values: `open` → `accepted` / `rejected` / `revoked` / `expired`.
- `used_by` / `used_at` — set when accepted or rejected by a known user.

**`MeetingGroupAnnotation`** — join table linking a `MeetingInvite` to a `MeetingGroup` (+ optional `GroupRole`). Stores pending group membership intent for invites that haven't been accepted yet.

## State machine (`statemachines.py`)

`InviteStateMachine(StateChart)` from `python-statemachine`. Bound to `MeetingInvite` via `StateMachineModelMixin`; access via `invite.sm` (built lazily on first access).

States (all final except `open`): `open` (initial), `accepted`, `rejected`, `revoked`, `expired`.

Events:
- `accept` — `open → accepted`. `after_accept` sets `used_by`/`used_at`, grants roles, calls `reg.run_accepted()`.
- `reject` — `open → rejected`. `after_reject` sets `used_by` if user has a pk.
- `revoke` — `open → revoked`. Validator `has_change_permission` raises `PermissionDenied` unless the caller has `invites.change_meetinginvite` on the invite. Pass `force=True` to skip the permission check (used internally, e.g. in tests).
- `expire` — `open → expired`. No permission guard (called from jobs/signals only).

`MeetingInvite.accept()`, `.reject()`, and `.revoke()` are thin wrappers that delegate to `self.sm`. State string values come from `InviteStateMachine.<state>.id` (e.g. `"open"`, `"accepted"`).

## Adapter system

All identity and annotation logic is pluggable via `InviteAdapterRegistry` (`registries.py`). Two adapter base classes in `abcs.py`:

- **`InviteUserDataAdapter`** — identity data (e.g. `email`, `swedish_ssn`). Used for querying invites and masking sensitive data in auditlog. Must not clash on schema field names; registry enforces this at registration time.
- **`AnnotationDataAdapter`** — secondary effect data (e.g. `group`, `grouprole`). Has `preflight`, `validate`, `check_conflicting_rows`, `annotate`, `accepted`, `clear`, `get_annotations` hooks.

Built-in adapters under `app/invites/`:
- `InviteEmail` — email identity, normalises to lowercase.
- `InviteGroup` — group annotation; applies `GroupMembership` on accept. Handles grouprole too.
- `InviteGroupRole` — must appear immediately after a `group` column; delegates all logic to `InviteGroup`.
- `InviteSweSSN` — Swedish personal number identity.
- `InviteParticipantNumber` — participant number annotation.

Registry is a singleton at `registries.invite_adapter_registry`. Access it via `utils.get_invite_adapter_registry()` to avoid circular imports.

## Data flow: creating invites

Two REST entry points feed the same write path. Both paths run the same registry validation pipeline:

1. `check_column_req` — validates column names and cross-column requirements (e.g. `grouprole` requires `group` to its left).
2. `preflight` — transforms data in-place (normalise case, strip whitespace, validate format). Must not touch the DB.
3. `check_intersections` — rejects rows where a single identity value appears in multiple distinct user_data subsets (identity columns only).
4. `check_conflicting_roles` — file imports only: rejects files where the same identity appears on rows with different roles. Repeating an identity is otherwise fine (one row per group), but rows are grouped by role combination when written, so conflicting roles would let the last combination silently win.
5. `check_conflicting_annotations` — rejects rows that collapse into the same annotation record but disagree about its content, which would let a later row silently overwrite an earlier one. Runs after `preflight`, so values are already normalised. Each `AnnotationDataAdapter` opts in declaratively: `collapse_key_columns` names the columns that (with the row identity) identify the record written, `no_overwrite_columns` names the columns that must then agree. `InviteGroup` sets `("group",)` / `("grouprole",)`; a blank value counts as a distinct value, since collapsing would drop the role. Raises `DataColValidationError` with a `message` explaining which rows and values clash. Repeating a row verbatim stays fine, and a stored grouprole may still be corrected by a later import.

Write path: `MeetingInviteManager.create_or_update_mixed`:
- Finds existing exact-match invites and updates roles / re-opens them if needed.
- Syncs roles on already-accepted invites via `_update_assigned_roles`.
- Bulk-creates new invites for unmatched rows.
- Returns `InviteResult(pks, added, changed, existed)`.

## Data flow: annotations

Annotations are applied alongside invite creation via the JSON REST endpoint or the file import endpoint. Identity and annotation keys are mixed flat in the same row/item; the registry distinguishes them. `registry.run_annotations()` is called after invites are written.

`InviteGroup.annotate()`:
- Already-accepted invites → `GroupMembership` created/updated immediately (per-invite, signals fire).
- Pending invites → `MeetingGroupAnnotation` bulk-created (no signals). Applied later in `InviteGroup.accepted()`.

## Invite lifecycle signals / side effects

`signals.py`:
- `archive_meeting` → expire all open invites for that meeting.
- `meeting_joined` → auto-accept any open email invite matching the user.
- `pre_delete` on `MeetingRoles` → delete all used invites for that user+meeting.
- `post_save` / `pre_delete` on `MeetingInvite` → publish WS messages on `MeetingInvitesChannel`.
- `invites.invites` collector on `MeetingInvitesChannel` → all current invites as one `meeting_invite.changed.batch` on subscribe.

## WebSocket messages (`messages.py`)

Outgoing only:
- `meeting_invite.changed` / `meeting_invite.deleted` — per-invite state changes pushed to `MeetingInvitesChannel`. There is no `.added`; the client upserts on `pk`.

`user_data` in outgoing messages is masked via `InviteAddedOrUpdatedSchema.mask_sensitive`.

## Scheduled jobs (`jobs.py`)

- `expire_unused_invites` (03:30 daily) — expires open invites where the meeting closed >30 days ago and the invite is >30 days old.
- `cleanup_invites` (03:50 daily) — deletes expired/revoked invites >30 days old and all invites >200 days old.

## REST API

See `rest_api/CLAUDE.md` for details. Summary:
- `/api/meeting-invites/` — moderator CRUD + bulk actions.
- `/api/match-invites/` — ID-proxy service endpoint (API key auth).
- `/api/handle-matched-invites/` — authenticated user accept/reject.
- `/api/invite-data-types/` — lists available adapter types.

## Permissions

- Add/change/delete `MeetingInvite`: requires `is_moderator & meeting_not_archived`.
- `accept` and `reject`: no object-level permission — auth is enforced entirely via queryset scoping in the calling ViewSet.
- `revoke`: permission checked inside the state machine via the `has_change_permission` validator (`invites.change_meetinginvite`, i.e. moderator). Pass `force=True` to bypass (internal use only).

## Dialect integration

`MeetingInviteManager._ignore_roles` reads `block_roles` from the meeting's installed dialect. Roles in that set are excluded when creating or syncing invite roles. This prevents dialects from overriding certain roles via the invite system.

## Management command

`import_invites` — imports invites (and optional annotations) from a file or stdin. Same pipeline as the file-upload REST endpoint: `detect_and_parse_file` → `extract_roles_per_row` → `RowColInvitesBaseSchema` → groupby-roles → `run_annotations`. Supports `--dryrun`.

## Testing fixtures

`testing.py` exposes `fixture_file(name)` and `get_unvalidated_fixture_content(name)` for loading fixtures from `tests/fixtures/`.
