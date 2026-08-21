# voteit.meeting

Manages meetings and their participants. A Meeting is the primary context for all democratic activity — agenda items, polls, proposals, and discussions all hang off a Meeting. This app owns: the Meeting model and its state machine, the role/group systems, REST endpoints, WebSocket channels, and the dialect configuration system.

## Models

### Meeting
Central model. Key fields:
- `state` — drives `MeetingStateMachine` (see State Machine below); access via `meeting.sm`
- `group_votes_active` / `group_roles_active` — toggles for group delegation and dynamic role assignment
- `er_policy_name` — references an electoral register policy from the registry
- `installed_dialect` — name of the currently installed dialect (just a name, handler re-instantiated from registry on demand)
- `archive_after` / `delete_requested` / `pre_delete_state` — managed by state transitions; do not set directly

### MeetingRoles
Join table between `User` and `Meeting`. The `assigned` field (`RolesField`, PostgreSQL `ArrayField`) holds the user's roles within that meeting. One row per user per meeting (`unique_together`). Changes to this model fire `roles_added` / `roles_removed` signals that drive WebSocket pushes.

### MeetingGroup
A named group within a meeting (e.g. delegation). `votes` is the group's total voting power. `delegate_to` delegates that power to another group (self-delegation and circular chains are blocked by serializer validation). Changing `votes` on a group may zero out individual `GroupMembership.votes` if they exceed the new total (enforced by `adjust_membership_voting_power_when_group_changes` signal).

### GroupMembership
Through-model for `MeetingGroup.members` (M2M). Holds `role` (FK to `GroupRole`, nullable) and `votes` (the member's allocated share of the group's voting power). Saving/deleting this fires `group_role_added` / `group_role_removed` signals, which cascade into adding/removing meeting-level roles from `MeetingRoles`.

> **M2M quirk**: Django doesn't fire through-model `post_save` when using `.members.add()` / `.members.remove()`. `compat_m2m_publish_group_membership` in `signals.py` compensates — it listens on `m2m_changed` and manually fires the expected through-model signals.

### GroupRole
A named role type within a meeting. Its `roles` field lists which `MeetingRoles` roles members automatically receive. When a user is assigned a `GroupRole` the `handle_meeting_roles_through_role_added` signal handler promotes those roles onto their `MeetingRoles`. Removal is symmetric but checks all other group memberships first to avoid revoking a role still granted by another group.

## Roles

Defined in `roles.py`. All non-participant roles require `ROLE_PARTICIPANT`:

| Code | Name | Constant |
|------|------|----------|
| `pa` | Participant | `ROLE_PARTICIPANT` |
| `mo` | Moderator | `ROLE_MODERATOR` |
| `pv` | Potential Voter | `ROLE_POTENTIAL_VOTER` |
| `di` | Discusser | `ROLE_DISCUSSER` |
| `pr` | Proposer | `ROLE_PROPOSER` |

## State Machine

`MeetingStateMachine` (in `statemachines.py`) states: `upcoming → ongoing ↔ closed → archiving → archived`, plus `deleting` reachable from any state. Key guards:
- `make_ongoing` event requires a valid electoral register policy (`validate_er_policy` validator)
- `close` event requires no ongoing polls (`no_ongoing_polls` validator)
- `request_archiving` event sets `archive_after = now + 3 days`; archived by background task
- `request_delete` / `abort_delete` events store and restore the previous state in `pre_delete_state`

State transitions are triggered via `meeting.sm.send(event_name, ...)` or the `POST /meetings/{id}/event/` REST endpoint (`StateMachineMixin`).

## REST API

ViewSets live in `rest_api/views.py`, all registered to the central router.

| Endpoint prefix | ViewSet | Notes |
|-----------------|---------|-------|
| `meetings/` | `MeetingViewSet` | CRUD + `set-agenda-order`, `install-dialect`, `remove-dialect` actions |
| `meeting-roles/` | `MeetingRolesViewSet` | List-only; use `add/` and `remove/` actions for mutations |
| `meeting-groups/` | `MeetingGroupViewSet` | List forbidden (no queryset); fetch via meeting detail |
| `group-memberships/` | `GroupMembershipViewSet` | List forbidden; `perform_update` manually tracks role changes to fire signals |
| `export-participants/` | `ExportParticipantsViewSet` | CSV/JSON export; requires `ROLE_MODERATOR` |
| `export-meeting-groups/` | `ExportMeetingGroupsViewSet` | CSV/JSON export; requires `ROLE_MODERATOR` |
| `meeting-dialects/` | `MeetingDialectsViewSet` | Read-only list of org-installable dialects |

`CreateMeetingSerializer` optionally accepts nested `room` and `speaker_list_system` payloads and installs them along with the dialect in one atomic operation.

Changing `er_policy_name` via `MeetingDetailSerializer` is blocked if any poll is ongoing (validated in `validate_er_policy_name`).

## WebSocket Channels

Three channels in `channels.py`, all scoped to a `Meeting` pk:

- **`meeting`** — general channel; all role/group/membership changes broadcast here
- **`participants`** — non-moderator view; receives non-private polls and agenda items only
- **`moderators`** — moderator-only; receives everything including private items

On `channel_subscribed`, the `meeting_channel_subscribed` signal handler pushes the subscriber's current roles, all groups, all group memberships, and (if active) all group roles in one burst.

## Signals

`signals.py` wires everything together. Key chains:

1. `MeetingRoles` created → `meeting_joined` (deferred to transaction commit)
2. `MeetingRoles` deleted → cascade delete `GroupMembership` for that user
3. `GroupMembership` saved/deleted → `group_role_added` / `group_role_removed` → updates `MeetingRoles`
4. `MeetingRoles` roles changed → `RolesChanged` / `RolesRemoved` pushed to `meeting` and user channels (deltas, not upserts)
5. `Meeting` / `MeetingGroup` / `GroupMembership` saved → corresponding `Changed` message pushed to `meeting` channel
6. Any of the above deleted → `Deleted` message pushed (via `pre_delete`, deferred to commit)

All signal handlers that publish messages defer via `on_transaction_commit=True` to avoid pushing before the DB row is visible.

## Dialects

`DialectRegistry` (`dialects.py`) is a lazy-loading dict keyed by dialect name. Dialects are YAML files under `MEETING_DIALECTS_DIR`. The registry auto-reloads if the directory mtime changes or is >1 min stale.

`install_dialect` action on `MeetingViewSet` is only available when the meeting is `upcoming` and no dialect is already installed. `remove_dialect` is symmetric.

`DialectHandler.install(meeting)` may create groups, assign components, and update meeting fields. The `installed_dialect` field only stores the name; call `registry.get_merged_handler(name)` to get a handler (which resolves the dependency chain).

## Permissions

Defined in `rules.py` using the `rules` library. Notable:

- `Meeting.VIEW` → `is_participant` (public meetings are NOT view-permissioned this way; use `PREVIEW` for unauthenticated/non-participant access)
- `Meeting.MODERATE` → `is_moderator`
- `Meeting.CHANGE_ROLES` → `is_moderator | is_manager` (org manager can also manage roles)
- `Meeting.PERM_CHANGE_DIALECT` → `meeting_upcoming & is_moderator`
- Group/membership permissions → `meeting_not_archived & is_moderator`

`is_moderator` is marked non-negatable — use explicit state predicates if you need "not moderator".

Two custom permission constants are exported from `__init__.py`: `PERM_CHANGE_DIALECT` and `PERM_PREVIEW`.
