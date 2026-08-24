# voteit.room

Provides a "Room" — a moderator-controlled live display surface within a meeting. A Room acts as a real-time projection screen: moderators drive it by pointing it at an agenda item, a poll, highlighted proposals, and speaker-list content. The frontend reads the room state to render what is currently "on screen" for participants. A meeting can have multiple rooms (e.g. one per physical screen or breakout session).

## Models

### Room (`models.py`)

Key fields:
- `meeting` — FK to `Meeting` (CASCADE); `related_name="rooms"`.
- `open` — whether the room is visible/active for participants. Automatically set to `True` on the first `handle` action if it was `False`.
- `handler` — FK to `AUTH_USER_MODEL` (SET_NULL); the moderator currently driving the room ("in the driver's seat"). Automatically reassigned to the requesting user on each `handle` action.
- `title`, `body` — display text; `body` is a `RichTextField` with `relaxed_clean_html` sanitisation.
- `agenda_item` — optional FK to `AgendaItem` (SET_NULL); the current agenda item in focus.
- `poll` — optional FK to `Poll` (SET_NULL); the active poll being shown.
- `show_ballot` — whether to show the ballot UI. Automatically reset to `False` whenever `poll` changes to a different value (enforced in `Room.save()`).
- `send_sls` — whether to stream speaker list changes to the room.
- `send_proposals` — whether to stream proposal updates to the room.
- `show_time` — whether to show a clock (e.g. for pause breaks; not related to the speaker list).
- `created` — auto-set on creation; not editable.

Non-obvious behaviour:
- `Room.__init__` captures `self.poll` and `self.show_ballot` as `_initial_poll_value` / `_initial_show_ballot`. `Room.save()` uses these to detect a poll change and clear `show_ballot` automatically.
- `Room.token` is a transient, non-persisted attribute. It is set on the instance during a `handle` or `highlighted` update so the originating WebSocket client can correlate the broadcast response with its own request. Never stored in the database.
- `Room.speaker_system` property returns the associated `SpeakerListSystem` (via the `sls` reverse OneToOne accessor) suppressing `ObjectDoesNotExist`. Used to implement `SpeakerSystemContext`.
- `Room.signal_highlighted()` fires the custom `highlighted_proposals_changed` signal to decouple the model from signal wiring.
- Registered with `auditlog` (fields: `title`, `open`, `handler`, `meeting`, `body`, `send_sls`, `send_proposals`, `show_time`) and `@history_log("meeting__organisation")`.

### HighlightProposal (`models.py`)

A through-model for the ordered list of proposals currently highlighted in a room.

- `room` — FK to `Room` (CASCADE); `related_name="highlighted_proposals"`.
- `proposal` — FK to `Proposal` (CASCADE); `related_name="highlighted_in"`.
- `order` — positive small integer; auto-assigned on creation to `max(order) + 1` if not provided.
- Unique constraint: `(room, proposal)`.
- Default ordering: `["order"]`.

`Room.highlighted_proposal_pks` property returns an ordered list of proposal PKs via `.values_list("proposal", flat=True)`.

## Permissions (`rules.py`)

All permissions require the meeting to not be archived (`meeting_not_archived`).

| Permission | Predicate |
|---|---|
| `Room.ADD` | `meeting_not_archived & is_moderator` |
| `Room.VIEW` | `is_participant` — also used as the channel subscription gate |
| `Room.CHANGE` | `meeting_not_archived & is_moderator` |
| `Room.HANDLE` | `meeting_not_archived & is_moderator` |
| `Room.handle_speaker` | `meeting_not_archived & (is_moderator \| is_speaker_moderator)` |
| `Room.DELETE` | `meeting_not_archived & is_moderator` |

`ROOM_PERM_HANDLE_SPEAKER = "handle_speaker"` is exported from `__init__.py`. The `handle_speaker` permission intentionally allows speaker-list moderators (users with `ROLE_LIST_MODERATOR` on the associated `SpeakerListSystem`) to control a subset of room fields without being a meeting moderator.

## REST API (`rest_api/views.py`)

`RoomsViewSet` registered at `rooms/`. Uses `VerboseAutoPermissionViewSetMixin` and `ForceMeetingWithRoleFilter` (a `?meeting=<pk>` query parameter is required for list; returns 400 without it).

`get_queryset()` returns rooms where the user either has a meeting role **or** has any role on the associated `SpeakerListSystem`. This is how speaker moderators can see and access rooms they don't have a meeting role for.

| Method | URL | Action | Permission | Serializer |
|---|---|---|---|---|
| `GET` | `rooms/?meeting=<pk>` | `list` | `VIEW` (via queryset) | `RoomSerializer` |
| `POST` | `rooms/` | `create` | `ADD` (in serializer) | `CreateRoomSerializer` |
| `GET` | `rooms/<pk>/` | `retrieve` | `VIEW` (via queryset) | `RoomDetailSerializer` |
| `PATCH/PUT` | `rooms/<pk>/` | `partial_update` / `update` | `CHANGE` | `RoomDetailSerializer` |
| `PATCH` | `rooms/<pk>/handle/` | `handle` | `HANDLE` | `RoomHandleSerializer` |
| `PATCH` | `rooms/<pk>/handle-speaker/` | `handle_speaker` | `handle_speaker` | `SpeakerManagerRoomDetailSerializer` |
| `POST` | `rooms/<pk>/mark-text/` | `mark_text` | `HANDLE` | `RoomMarkTextSerializer` |
| `GET` | `rooms/<pk>/status/` | `status` | none (queryset) | — |
| `DELETE` | `rooms/<pk>/` | `destroy` | `DELETE` | — |

Notable action behaviour:
- `handle` — the primary moderator action. Updates `highlighted`, `poll`, `agenda_item`, `send_proposals`, `show_ballot`. Automatically sets `open=True` and reassigns `handler` to the requesting user. Uses `select_for_update()` to prevent concurrent order corruption on `highlighted_proposals`.
- `handle_speaker` — restricted fields: `body`, `open`, `show_time`, `send_sls`. Only the speaker-list moderator fields.
- `mark_text` — relays a text selection (`start`, `end`, `proposal`) to `RoomChannel` subscribers via a `RoomMarked` WebSocket message. Nothing is persisted; validated by `RoomMarkTextSerializer` (start/end must both be set or both be `None`; `proposal` is required if start/end are given — same rules as the retired `RoomMarkTextSchema`-based WebSocket message).
- `status` — preflight check returning `{"speakers": N, "speaker_lists": N}` to let the frontend warn before deleting a room with active speaker data.
- `destroy` — deletes the associated `SpeakerListSystem` first (cascades speakers), then the room. Both happen inside a `durable=True` atomic block.

### Serializers (`rest_api/serializers.py`)

- `RoomSerializer` — all fields read-only; used for list output and as the base class.
- `CreateRoomSerializer` — all fields writable except `handler`. Validates meeting ADD permission via `validate_model_add`. Wrapped in `@ensure_atomic`.
- `RoomDetailSerializer` — all fields writable except `handler` and `meeting` (read-only); used for retrieve and full update. Wrapped in `@ensure_atomic`.
- `RoomHandleSerializer` — accepts `highlighted` (list of proposal PKs), `poll`, `agenda_item`, `send_proposals`, `show_ballot`, `token`. Validates that all highlighted PKs belong to the same meeting. The `update()` method only calls `super().update()` when non-highlighted fields have actually changed, preventing redundant `post_save` signals.
- `SpeakerManagerRoomDetailSerializer` — restricts writable fields to `body`, `open`, `show_time`, `send_sls`.
- `RoomMarkTextSerializer` — plain (non-model) serializer for the `mark_text` action; `start`, `end`, `proposal` all optional/nullable with the same cross-field validation as `RoomMarkTextSchema`.

## WebSocket

### Channel (`channels.py`)

`RoomChannel` — a `ContextChannel` keyed on `Room.pk`. Permission gate: `Room.VIEW`. Registered via `@channel` decorator.

### Messages (`messages.py`)

All messages are outgoing, published via `broadcast_meeting` (for room-level CRUD) or `RoomChannel` (for highlighted-proposals updates and text marking):

| Message name | Class | Channel | Payload |
|---|---|---|---|
| `room.changed` | `RoomChanged` | `broadcast_meeting` | Full room serializer data + optional `token`. There is no `room.added`; the client upserts on `pk`. |
| `room.deleted` | `RoomDeleted` | `broadcast_meeting` | `pk` only |
| `room.highlighted` | `RoomHighlighted` | `RoomChannel` | `{pk, highlighted: [int], token}` |
| `room.marked` | `RoomMarked` | `RoomChannel` | `{room, start, end, proposal}` |

`RoomMarked` is published from the REST `mark_text` action (see REST API above), not from a WebSocket-incoming message — there is no incoming message in this app.

### Signal handlers (`signals.py`)

- `room.rooms` collector on `ParticipantsChannel` + `ModeratorsChannel` — all rooms for the meeting as one `room.changed.batch`.
- `room.highlighted` collector on `RoomChannel` — a `RoomHighlighted` message with the current `highlighted_proposal_pks`.
- `post_save` on `Room` — publishes `RoomChanged` via `broadcast_meeting` on create and update. Decorated with `@disable_on_raw_save`.
- `pre_delete` on `Room` — publishes `RoomDeleted` via `broadcast_meeting`.
- `highlighted_proposals_changed` signal — publishes `RoomHighlighted` (with token) to `RoomChannel`.

The custom `highlighted_proposals_changed = Signal()` is defined in `signals.py` and fired by `Room.signal_highlighted()`. This keeps signal wiring out of the model.

## Non-obvious design decisions

### Two separate permission tracks for room control
The `HANDLE` permission (full room control: poll, proposals, agenda item) and `handle_speaker` permission (body, speaker list flags) are split so that speaker-list moderators — who are not meeting-wide moderators — can drive the content relevant to their role without gaining broader room control. The `get_queryset` override in the view includes rooms accessible via speaker-system roles so these users can even see the rooms.

### `handle` sets `open` and `handler` implicitly
Sending a PATCH to `handle/` always claims the room: `open` is forced to `True` and `handler` is set to the requesting user. The client does not need to set these explicitly. This prevents a room from silently staying closed when a moderator starts working on it.

### Highlighted proposals use `bulk_create` with `update_conflicts`
`RoomHandleSerializer.update()` uses `bulk_create(..., update_conflicts=True, update_fields=["order"])` to upsert `HighlightProposal` rows in a single query, then deletes removed rows. The operation is wrapped in `select_for_update()` on the room to prevent two concurrent requests corrupting the order values.

### Save is skipped when nothing changed
`RoomHandleSerializer.update()` deliberately avoids calling `super().update()` (which would call `Room.save()`) when the only change was to `highlighted`. This prevents an unnecessary `post_save` signal (and its WebSocket broadcast) when only proposal highlighting changed — the highlight broadcast is already sent independently via `signal_highlighted()`.

### `show_ballot` is reset automatically on poll change
`Room.save()` tracks the poll FK value at `__init__` time and clears `show_ballot` whenever the poll FK changes to a different value. This prevents a stale "show ballot" state after a moderator switches to a different poll.

### `token` is a transient instance attribute
`Room.token` is never persisted. It is attached to the model instance during a request by the serializer (`instance.token = validated_data.pop("token", None)`) so that signal handlers can include it in the outgoing WebSocket message. The frontend uses the token to correlate its own request with the resulting broadcast and suppress duplicate UI updates.

### `mark_text` does not persist anything
The `mark_text` REST action relays text selection coordinates to all subscribers of a `RoomChannel` without storing anything on the `Room`. Unlike its retired WebSocket-message predecessor (which silently swallowed permission failures to avoid noise for moderators rapidly selecting text), the REST action uses the normal `VerboseAutoPermissionViewSetMixin` permission check and returns a standard 403 on failure.

## Tests

```bash
python manage.py test voteit.room --keepdb --failfast
```

Test modules:
- `tests/test_models.py` — `Room` creation; `HighlightProposal` duplicate constraint and auto-ordering.
- `tests/test_rules.py` — ADD / CHANGE / DELETE / HANDLE permissions for anonymous, participant, and moderator roles; archived-meeting blocks.
- `tests/test_signals.py` — WebSocket messages on room create/update/delete; `ParticipantsChannel` subscription sends `RoomChanged`; `RoomChannel` subscription sends `RoomHighlighted`; N+1 query guard on room subscription.
- `tests/test_docs.py` — runs doctests defined in the `voteit.room` package (currently covers `RoomMarkTextSchema` validation).
- `rest_api/tests/test_views.py` — full CRUD, permission checks, `handle` action (highlighted order, deduplication, cross-meeting rejection, token propagation, auto-open, auto-handler), `handle_speaker` scoping, `status` preflight, delete with SLS cascade.
- `rest_api/tests/test_serializers.py` — `RoomDetailSerializer` field output; `RoomHandleSerializer` with/without highlights, bad PKs, cross-meeting proposals.
