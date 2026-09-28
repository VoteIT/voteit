# voteit.agenda

Manages the `AgendaItem` model — the structural unit within a `Meeting`. Each agenda item is a discussion/voting container holding proposals, polls, and discussion posts.

## Models

### AgendaItem

State machine model (`AgendaItemStateMachine`). Key fields:
- `state` — initial state is `private`; access state machine via `agenda_item.sm`
- `order` — auto-assigned as next sequential value per meeting on creation
- `block_discussion` / `block_proposals` — moderator flags that prevent new content
`related_modified` is **not a column**. `AgendaItem.objects.with_related_modified()` annotates it as the newest `created` among the item's proposals and discussion posts (edits don't count); `get_related_modified()` uses the annotation or queries for it. The frontend compares it against `LastRead.timestamp` to show "unread" indicators. Querysets that feed `AgendaItemSerializer` / `AgendaItemListSerializer` in bulk should be annotated, or each row costs a query.

When a proposal (any subclass) or discussion post is created or deleted, `signals.py` schedules a `RelatedModifiedPush` on commit: one `AgendaChanged` per touched agenda item per transaction, read fresh from the database. Items deleted in the same transaction aren't found, so a cascade can't resurrect them client side.

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
- `BulkAgendaItemSerializer` / `BulkAgendaItemChangeSerializer` / `BulkAgendaItemDeleteSerializer` — used by the bulk actions below; `meeting` is a `ModeratorMeetingField` so non-moderators get a 400 (field-level rejection) rather than a 403

`ExportAgendaItemsViewSet` at `export-agenda-items/` — moderator-only CSV/JSON export.

### Bulk actions

- `POST /agenda-items/bulk-change/` — `{"meeting": 1, "agenda_items": [1,2,3], "state": "ongoing", "block_discussion": true, "block_proposals": true}` (at least one of `state`/`block_discussion`/`block_proposals` required). State changes go through `ai.sm.send(...)` (same guards as the single-item `/event/` endpoint), so items where the transition isn't allowed are silently skipped rather than raising. Returns `{"changed": N}` — the count of items actually saved (deduped across the three fields, so an item touched on two axes only counts/saves once).
- `POST /agenda-items/bulk-delete/` — `{"meeting": 1, "agenda_items": [1,2,3]}`. Blocked (400) if the meeting is ONGOING. Returns `{"deleted": N}`.
- Both cap `agenda_items` at 250 entries — the state-machine guards (`has_change_permission`, `no_ongoing_polls`) run once per item, so this bounds worst-case query count. The item-fetch/validation step itself is a single query regardless of list size (`ai.meeting` is assigned from the already-validated `meeting` field to avoid a per-item FK query in the `meeting_is_ongoing`/`meeting_not_upcoming` guards).

## WebSocket (channels.py / messages.py)

**`AgendaItemChannel`** — per-item channel; permission `agenda.view_agendaitem`. Sends full body on subscription.

**Outgoing broadcasts via signals (signals.py):**
- `AgendaChanged` / `AgendaDeleted` → `ParticipantsChannel` (non-private only) and `ModeratorsChannel` (all). There is no `*.added`; the client upserts on `pk`.
- `AgendaBodyChanged` / `AgendaBodyDeleted` → `AgendaItemChannel`
- When an item becomes PRIVATE, `AgendaDeleted` is sent to `ParticipantsChannel` to hide it from non-moderators

All signal-based messages are deferred to transaction commit (`@on_commit`). Bulk operations use `@disable_on_raw_save` to suppress signals.

## Notable Patterns

- **Visibility routing:** Private items are actively deleted from participant views on transition to PRIVATE (not just withheld). `signals.py:ai_made_private` handles this.
- **Order assignment:** Only set on first save (when not provided). Computed as `max(order) + 1` for the meeting.
- **Serializer split by audience:** List views use `AgendaItemListSerializer` (no body), detail/channel uses full serializer. Body updates go through `AgendaItemBodySerializer` on the item channel separately.
