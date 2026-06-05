# voteit.agenda

Manages the `AgendaItem` model — the structural unit within a `Meeting`. Each agenda item is a discussion/voting container holding proposals, polls, and discussion posts.

## Models

### AgendaItem

State machine model (`AgendaItemStateMachine`). Key fields:
- `state` — initial state is `private`; access state machine via `agenda_item.sm`
- `order` — auto-assigned as next sequential value per meeting on creation
- `block_discussion` / `block_proposals` — moderator flags that prevent new content
- `related_modified` — timestamp updated when nested proposals/discussions are created; frontend compares this against `LastRead.timestamp` to show "unread" indicators

`related_modified` has a 3-second debounce (`maybe_mark_related_modified`). On delete of nested content, `revert_to_last_related_modified` walks the remaining items and sets it back to the most recent modification date (or clears it if nothing remains).

### LastRead

One record per `(user, agenda_item, meeting)`. Created/updated by `mark_read()`. Auto-populates `meeting` from `agenda_item.meeting` on save.

## State Machine

`AgendaItemStateMachine` in `statemachines.py`. States: `private → upcoming → ongoing → closed → archived`

| Event | From | Guard |
|---|---|---|
| `make_upcoming` | private, closed, ongoing | no ongoing polls; `has_change_permission` |
| `unpublish` | upcoming, closed, ongoing | no ongoing polls; `has_change_permission` |
| `make_ongoing` | private, upcoming, closed | meeting must be ongoing; `has_change_permission` |
| `close` | private, upcoming, ongoing | no ongoing polls; `has_change_permission` |
| `archive` | any | `force=True` only (script-only, raises `PermissionDenied` for users) |

`archive` is triggered by the `archive_agenda_items` signal when the meeting is archived. Events are sent via `ai.sm.send(event_name, ...)` or `POST /agenda-items/{id}/event/` (`StateMachineMixin`).

## Permissions (rules.py)

| Permission | Who |
|---|---|
| `agenda.view_agendaitem` | Moderators always; others only when item is non-PRIVATE and they can view the meeting |
| `agenda.add_agendaitem` | Moderator, meeting not archived |
| `agenda.change_agendaitem` | Moderator, meeting not archived |
| `agenda.delete_agendaitem` | Moderator, meeting not archived |

State machine events use `agenda.change_agendaitem` as the permission guard.

## REST API (rest_api/)

`AgendaViewSet` at `agenda-items/`. Queryset hides private items from non-moderators. Uses `StateMachineMixin` for state transitions at `POST /agenda-items/{id}/event/`.

Serializers:
- `AgendaItemSerializer` — full detail (read-only: meeting, order, related_modified, state, pk)
- `AgendaItemListSerializer` — abbreviated, no body
- `AgendaItemBodySerializer` — body + pk only
- `CreateAgendaItemSerializer` — writable, used on POST

`ExportAgendaItemsViewSet` at `export-agenda-items/` — moderator-only CSV/JSON export.

## WebSocket (channels.py / messages.py)

**`AgendaItemChannel`** — per-item channel; permission `agenda.view_agendaitem`. Sends full body on subscription.

**Incoming messages:**
- `last_read.change` — marks item read, returns `LastReadChanged`
- `agenda_item.bulk_update` — bulk state/block_discussion/block_proposals change (skips items where transition is invalid)
- `agenda_item.bulk_delete` — bulk delete; blocked if meeting is ONGOING

**Outgoing broadcasts via signals (signals.py):**
- `AgendaAdded` / `AgendaChanged` / `AgendaDeleted` → `ParticipantsChannel` (non-private only) and `ModeratorsChannel` (all)
- `AgendaBodyAdded` / `AgendaBodyChanged` / `AgendaBodyDeleted` → `AgendaItemChannel`
- When an item becomes PRIVATE, `AgendaDeleted` is sent to `ParticipantsChannel` to hide it from non-moderators

All signal-based messages are deferred to transaction commit (`@on_commit`). Bulk operations use `@disable_on_raw_save` to suppress signals.

## Notable Patterns

- **Visibility routing:** Private items are actively deleted from participant views on transition to PRIVATE (not just withheld). `signals.py:ai_made_private` handles this.
- **Order assignment:** Only set on first save (when not provided). Computed as `max(order) + 1` for the meeting.
- **`related_modified` debounce:** Prevents redundant WebSocket pushes when many proposals are created quickly (e.g., bulk import). The 3-second window is intentional.
- **Serializer split by audience:** List views use `AgendaItemListSerializer` (no body), detail/channel uses full serializer. Body updates go through `AgendaItemBodySerializer` on the item channel separately.
