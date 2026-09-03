# voteit.speaker

Manages speaker queues (speaker lists) for meetings. A `SpeakerListSystem` belongs to a `Room` and holds one or more `SpeakerList` objects. Participants enter and leave lists, moderators start and stop individual speakers, and the ordering of speakers in the queue is controlled by a pluggable list method. The app supports real-time state delivery via WebSocket channels and exports of the complete speaking history.

## Models

### SpeakerListSystem

The system-level container for all speaker list activity within a room. One room has at most one `SpeakerListSystem` (enforced by `OneToOneField`).

Key fields:
- `state` — drives `SpeakerSystemStateMachine`; access via `instance.sm`
- `room` — `OneToOneField` to `Room`; the system and its room must share the same meeting
- `meeting` — auto-populated from `room.meeting_id` on first save if not set
- `method_name` — key into the `list_method` registry; determines ordering algorithm
- `settings_data` — JSONField storing the method's `settings_schema` Pydantic model as a dict; access/set via the `settings` property
- `active_list` — `OneToOneField` (nullable) to the currently displayed `SpeakerList`; setting this triggers `active_list_changed` signal
- `meeting_roles_to_speaker` — `RolesField`; any meeting role listed here automatically qualifies a user to enter the queue (without needing an explicit `ROLE_SPEAKER`)
- `safe_positions` — integer (0–2); top N queue positions are never reordered by the method. If the current speaker occupies position ≤ N, one extra position is reserved.
- `show_time` — whether clients should display time-spoken counters

The `settings` property validates against the method's `settings_schema` on read and write. Setting it from a plain dict validates and serialises through Pydantic.

`method_name_changed` and `active_list_changed` properties detect in-memory dirty state (compared against `_initial_*` values captured on load). `save()` fires `list_method_added`/`list_method_removed` signals when the method changes, and `active_list_changed` when the active list changes.

`archive()` sets state directly (bypassing the state machine), clears the active list, deletes all pending (un-spoken) `Speaker` entries, and empties the `order` field on all lists.

### SpeakerList

A named queue attached to a `SpeakerListSystem`. May optionally be tied to an `AgendaItem`.

Key fields:
- `is_open` — controls whether participants can enter
- `order` — comma-separated user PKs; the canonical queue ordering; access via `order_list` property
- `speaker_system`, `meeting`, `room` — `room` and `meeting` are auto-populated from `speaker_system` on first save
- `agenda_item` — optional; cross-meeting integrity checked on save

`reorder(order_list=None)` re-runs the list method and saves only when the computed order differs from the current one. The method receives all in-queue-or-speaking speakers sorted by: existing position in `order_list`, then by `created` timestamp for newcomers.

`is_active_list` is a cached Boolean property. The cache is invalidated by `refresh_from_db()`. `SpeakerListSystem.save()` writes `True` directly onto the active list's cache to avoid an extra query.

`shuffle()` randomises the order, then calls `reorder()` so method-enforced priorities are applied afterwards.

### Speaker

A through-model for `SpeakerList.speakers` (M2M). One row per user per list per speaking turn. A user may appear multiple times on the same list (each turn after speaking creates a new entry).

Key fields:
- `started` — set when the speaker begins; `None` means they are still in the queue
- `seconds` — set when they finish; `None` means the turn is not yet complete (or not started)
- `created` — used as a tiebreaker when two speakers join at the "same" position

Status helpers: `current` (`started` not None, `seconds` None), `in_queue` (`started` is None), `ended` (computed as `started + timedelta(seconds=seconds)`).

Two database constraints:
- `only_one_ongoing_speaker` — at most one speaker per list may have `started` set and `seconds` null
- `only_unique_users_in_queue` — a user may only appear once per list in the queue (seconds is null); historical rows (seconds set) are unconstrained

`stop()` caps `seconds` at 32767 (max `PositiveSmallIntegerField`, ~9 hours); if a speaker was accidentally left active for a very long time, they are capped and the system remains consistent.

### SpeakerSystemRoles

Roles within a specific `SpeakerListSystem`. Extends the `Roles` abstract model with:
- `ROLE_LIST_MODERATOR` (`list_moderator`) — can moderate lists within this system; cannot activate/inactivate the system itself
- `ROLE_SPEAKER` (`speaker`) — can enter lists in this system

Adding any role to a user via this model automatically adds `ROLE_PARTICIPANT` to their meeting roles (signal handler `make_speaker_system_users_participants`). Conversely, removing `ROLE_PARTICIPANT` from the meeting cascades into removing all speaker system roles for that user.

## State Machine

`SpeakerSystemStateMachine` in `statemachines.py`. Initial state: `active`.

| State | Description |
|-------|-------------|
| `active` | Lists are open for use |
| `inactive` | System paused; no active list |
| `archived` | Final state; lists are cleared |

| Event | Transition | Guards |
|-------|------------|--------|
| `activate` | `inactive → active` | `has_change_permission` (meeting moderator) |
| `inactivate` | `active → inactive` | `has_change_permission`; `no_active_speaker` (no one currently speaking) |
| `archive` | `inactive/active → archived` | `not_allowed` (raises `PermissionDenied` — script-only) |

`on_inactivate` side effect: clears `active_list` to `None`.

Archiving is done by `SpeakerListSystem.archive()` which writes the state directly, bypassing the state machine guard. The `archive` event on the state machine is defined but guards against all callers to prevent API access.

State machine events are sent via `instance.sm.send(event_name, user=user)` or via the REST endpoint `POST /speaker-list-systems/{id}/event/`.

## List Methods

Pluggable ordering algorithms registered in `voteit.speaker.registries.list_method` (a `Registry[ListMethod]`). The ABC is in `abcs.py`. All built-in methods live in `app/list_methods/`.

| Name | Class | Settings | Description |
|------|-------|----------|-------------|
| `simple` | `Simple` | None | FIFO, no reordering |
| `priority` | `Priority` | `max_times` (int) | Speakers who have spoken fewer times are prioritised |
| `gender_prio` | `GenderAndPriority` | `max_times`, `priority_genders` | Priority by spoken count + alternating gender |

The `ListMethod` interface:
- `reorder(safe_speakers, incoming_order) -> Iterator[Speaker]` — receives speakers already sorted by current order; returns new order (not including safe speakers)
- `get_queryset(speaker_list) -> QuerySet` — returns speakers in queue or currently speaking; may annotate with extra attributes (e.g. `spoken_count`, `gender_tag`) needed by `reorder`
- `settings_schema` — optional Pydantic model class; if present, `SpeakerListSystem.settings` validates against it

`GenderAndPriority` hooks into `list_method_added` / `list_method_removed` signals to enable/disable the `GenderTags` meeting component automatically.

Register new methods by decorating the class with `@list_method` and importing it in `app/list_methods/__init__.py:register()`.

## Permissions

Defined in `rules.py` using the `rules` library. Custom permission suffixes are exported from `__init__.py`: `PERM_ENTER`, `PERM_SHUFFLE`, `PERM_START`.

**SpeakerList:**
| Permission | Who |
|------------|-----|
| `add` | Meeting moderator or list moderator, meeting upcoming/ongoing |
| `change` | Meeting moderator or list moderator, meeting upcoming/ongoing |
| `delete` | Meeting moderator or list moderator, system not archived |
| `enter` | List open, meeting upcoming/ongoing, not currently speaking, has speaker role or is moderator |
| `shuffle` | Meeting moderator or list moderator, meeting upcoming/ongoing |

**SpeakerListSystem:**
| Permission | Who |
|------------|-----|
| `add` | Moderator, meeting upcoming/ongoing (checked against meeting) |
| `change` | Moderator, system not archived |
| `delete` | Moderator, meeting upcoming/ongoing, system not archived, no active list |
| `change_roles` | Moderator, system not archived |
| `view_roles` | Any participant |

**Speaker:**
| Permission | Who |
|------------|-----|
| `add` | Moderator or list moderator, meeting upcoming/ongoing, system active |
| `change` | System not archived (qs filter handles moderator scoping) |
| `delete` | System not archived |
| `start` | Active list (qs filter handles moderator scoping) |

`has_speaker_role` checks `meeting_roles_to_speaker` first, then falls back to checking `ROLE_SPEAKER` or `ROLE_LIST_MODERATOR` on the system.

## REST API

All ViewSets registered to the central router at `voteit/core/rest_api/router.py`.

### `speaker-list-systems/` (`SpeakerListSystemViewSet`)

Full CRUD. `create` permission checked in serializer via `validate_room`. `retrieve` gated by queryset (`meeting__participants=request.user`). List action returns empty (detail-only access).

State machine events via `StateMachineMixin` at `POST /speaker-list-systems/{id}/event/` with body `{"event": "activate|inactivate"}`. List moderators cannot activate/inactivate — that requires meeting moderator.

`active_list` is writable on update but the field's queryset is scoped to lists belonging to that system only.

`settings` accepts a dict and is validated against the method's schema; unknown keys are silently discarded (Pydantic extra-fields behaviour). Methods without a schema (`simple`) ignore the `settings` field.

### `speaker-lists/` (`SpeakerListViewSet`)

Full CRUD. Retrieve gated by queryset (`meeting__participants`). List returns empty.

Custom actions (all require `select_for_update` via `get_update_object`):
- `POST /speaker-lists/{id}/enter/` — adds requesting user to the queue; idempotent (returns 200 if already present, 201 on create); triggers `reorder()`
- `POST /speaker-lists/{id}/leave/` — removes requesting user from queue (not from ongoing speaking); triggers `reorder()`; 404 if not in queue
- `POST /speaker-lists/{id}/shuffle/` — randomises queue; blocked if any speaker is currently active

### `speakers/` (`SpeakerViewSet`)

Full CRUD (list returns empty). Access scoped to meeting moderators and list moderators via queryset. Regular participants and speaker-role users cannot access individual `Speaker` objects — they manage themselves via the list `enter`/`leave` actions.

Custom actions:
- `POST /speakers/{id}/start/` — starts the speaker; if another speaker is already active, stops them first atomically
- `POST /speakers/{id}/stop/` — stops the current speaker; removes from order list
- `POST /speakers/{id}/undo/` — reverts a started speaker back to the queue (clears `started`); only valid if `seconds` is still null

Update (PATCH/PUT) is only permitted on completed speakers (`seconds` set).

### `speaker-history/` (`HistoricSpeakerViewSet`)

Read-only aggregated view. Returns `{user, times_spoken, seconds_spoken}` per user. Filterable by `speaker_system` and `meeting` (required). Only completed speaking turns (seconds set) are counted. Any authenticated meeting participant can query their own meeting's history.

### `speaker-system-roles/` (`SpeakerSystemRolesViewSet`)

List roles scoped to `meeting__participants`. Requires `context` filter (system pk). Supports `user_id_in` filter.

- `GET /speaker-system-roles/available/` — lists available roles (no auth required)
- `POST /speaker-system-roles/add/` — adds roles; requires `change_roles` on the system; auto-logs the change
- `POST /speaker-system-roles/remove/` — removes roles; returns 204 when the roles object is fully deleted

### `export-speakers/` (`ExportSpeakersViewSet`)

Export completed speaking turns for a system. Accessible to meeting moderators and list moderators.
- `GET /export-speakers/{id}/csv/` — returns CSV with speaker identity fields, timing, list name, agenda item
- `GET /export-speakers/{id}/json/` — same data as JSON

## WebSocket Messages

All messages in `messages.py` are outgoing only (`@outgoing`).

There is no `*.added` message; the client upserts on `*.changed`.

| Message | Name | When |
|---------|------|------|
| `SpeakerSystemChanged` | `speaker_system.changed` | System created or updated |
| `SpeakerSystemDeleted` | `speaker_system.deleted` | System deleted |
| `SpeakerListChanged` | `speaker_list.changed` | List created or updated, or active speaker changed |
| `SpeakerListDeleted` | `speaker_list.deleted` | List deleted |
| `SpeakerChanged` | `speaker.changed` | Speaker joins, or is updated (started/stopped) on, the active list |
| `SpeakerDeleted` | `speaker.deleted` | Speaker removed from active list |

`SpeakerSerializer` includes a denormalised `room` field (source: `speaker_list.room`) so clients can route messages without traversing the list.

The `active_list_changed` batch and the `speaker.active_list` collector both build their payloads with `collectors.speaker_payloads`, a `.values()` query whose field list is derived from `SpeakerSerializer.Meta.fields` (`room` becomes an `F("speaker_list__room_id")` alias, since it is not a column). `.values()` rather than the serializer because it is about 5x faster and uses 3x less memory; `tests/test_collectors.py::test_values_matches_the_serializer` holds that the two produce identical frames.

## Signals

Custom signals defined in `signals.py`:
- `active_list_changed(instance: SpeakerListSystem)` — fired when `active_list_id` changes; handler publishes `SpeakerListChanged` plus a pre-built `speaker.changed.batch` covering every existing speaker, to the `RoomChannel`. The batch is `speaker_payloads()` over the list's speakers
- `list_method_added(sender=method_class, instance: SpeakerListSystem)` — fired on method assignment or system creation
- `list_method_removed(sender=method_class, instance: SpeakerListSystem)` — fired on method change or system deletion

**Django signal receivers:**

- `post_save(SpeakerListSystem)` → `SpeakerSystemChanged` via `broadcast_meeting` (synchronous, no commit deferral)
- `pre_delete(SpeakerListSystem)` → `SpeakerSystemDeleted` via `broadcast_meeting`; also fires `list_method_removed`
- `post_save(SpeakerList)` → `SpeakerListChanged` on `AgendaItemChannel`; also on `RoomChannel` if it is the active list (deferred to commit)
- `pre_delete(SpeakerList)` → `SpeakerListDeleted` on `AgendaItemChannel`
- `post_save(Speaker)` → `SpeakerListChanged` on `AgendaItemChannel` and `RoomChannel` if active (when `started` or `seconds` changed); also `SpeakerChanged` on `RoomChannel` if active (deferred to commit)
- `pre_delete(Speaker)` → `SpeakerDeleted` on `RoomChannel` if active

**Cross-app signal receivers:**

- `before_sm_transition(AgendaItem, target=closed)` → blocks transition if any speaker is currently active on a list in that item
- `before_sm_transition(Meeting, target=closed/deleting)` → same check meeting-wide
- `after_sm_transition(AgendaItem, target=closed)` → closes all lists and deactivates any active list for that item
- `archive_meeting` → archives all systems in the meeting
- `roles_added(SpeakerSystemRoles)` → ensures user has `ROLE_PARTICIPANT` in the meeting; also pushes `RolesChanged` via `broadcast_meeting` and `UserChannel`
- `roles_removed(MeetingRoles, ROLE_PARTICIPANT in roles)` → removes all speaker system roles for that user from all systems in the meeting

**Initial state (collectors.py):**

- `speaker.systems` / `speaker.roles` (`ParticipantsChannel` + `ModeratorsChannel`) → all systems, and the user's roles within them
- `speaker.active_list` (`RoomChannel`) → the active list and its speakers; `applicable()` is False when the room has no system or no active list
- `speaker.lists` (`AgendaItemChannel`) → all active-system lists for that item

## Notable Design Decisions

**Active list vs. state machine:** The system has a state (`active`/`inactive`/`archived`) but also tracks which specific list is currently active via `active_list`. These are independent: an active system may have no active list, and setting `active_list = None` (on inactivate or manually) does not change the system state.

**Order as a denormalised text field:** `SpeakerList.order` stores speaker user PKs as a comma-separated string rather than a position column on `Speaker`. This avoids row-level locking during reorder and makes the entire queue readable in one field. The order is rebuilt by `reorder()` which sorts by existing position + entry timestamp.

**`only_unique_users_in_queue` constraint allows re-entry:** The unique constraint on `(user, speaker_list)` only applies when `seconds IS NULL`. Once a speaker finishes (`seconds` set), a new in-queue entry for the same user on the same list is allowed. This enables multiple speaking turns per list without deleting historical rows.

**`start` auto-stops the current speaker:** `POST /speakers/{id}/start/` will atomically stop any currently-active speaker before starting the new one. The stopped speaker is also removed from `order_list` immediately.

**Permission delegation pattern:** Many permission checks for `Speaker` CRUD are handled by queryset scoping rather than explicit permission classes. The `get_queryset` method returns only speakers that belong to lists in systems where the requesting user is a meeting moderator or list moderator. The `permission_type_map` sets these actions to `None` to skip the standard `VerboseAutoPermissionViewSetMixin` check.

**`active_list_changed` fires synchronously:** Unlike most other signal handlers (which defer to commit), the `notify_active_list_changed` receiver fires synchronously via `sync_publish`. This means the room channel is updated in the same request cycle as the system save.

**`SpeakerSystemStateMachine` initial state is `active`:** New systems start as active, not inactive. The `inactive` state exists for temporarily pausing a system without archiving it.

**`archive` event is intentionally broken for API callers:** The `not_allowed` validator on the `archive` event unconditionally raises `PermissionDenied`. Archiving is always triggered by `SpeakerListSystem.archive()` (called from `close_and_cleanup` on meeting archive), which writes the state directly.

## Tests

```bash
python manage.py test voteit.speaker --keepdb --failfast
```

Test modules:
- `tests/test_models.py` — unit tests for `Speaker`, `SpeakerList`, and `SpeakerListSystem` including constraints, reorder, archive, signals
- `tests/test_signals.py` — integration tests for WebSocket channel delivery; tests cross-app guards (AI/meeting close blocked by active speaker)
- `tests/test_list_method.py` — smoke tests for `shuffle()`
- `app/list_methods/tests/test_gender.py` — ordering tests for `GenderAndPriority`
- `app/list_methods/tests/test_priority.py` — ordering tests for `Priority`
- `rest_api/tests/test_views.py` — API permission and behaviour tests for all ViewSets
- `rest_api/tests/test_serializers.py` — serializer tests
- `tests/test_functional.py` — currently fully commented out (pending channel message infrastructure update)
