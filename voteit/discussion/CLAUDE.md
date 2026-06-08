# voteit.discussion

Manages `DiscussionPost` — free-text contributions that participants attach to a meeting's agenda items. Posts are the primary discussion mechanism: participants (with the Discusser role) and moderators submit rich-text entries; moderators can edit or delete any post while authors can only delete their own. There is no state machine — posts are immutable after creation except for moderator edits.

## Tests

```bash
python manage.py test voteit.discussion --keepdb --failfast
```

## Models

### DiscussionPost

Inherits `BaseContent` (provides `body`, `created`, `modified`, `mentions`, `tags`), `AgendaItemContext`, `MeetingContext`, and `Reactable`.

Key fields:
- `author` — `ForeignKey` to `AUTH_USER_MODEL`; nullable (`SET_NULL` on delete is on `BaseContent.author`, this FK is `RESTRICT`). Can be reassigned by moderators.
- `agenda_item` — `ForeignKey` to `AgendaItem`; `CASCADE` on delete.
- `meeting_group` — optional `ForeignKey` to `MeetingGroup`; `RESTRICT` on delete.
- `as_group` — boolean flag indicating the post speaks on behalf of `meeting_group` rather than the individual author. Automatically cleared by `save()` if `meeting_group` is not set.

`meeting` is a computed property that traverses `agenda_item.meeting` — there is no direct FK to `Meeting`.

The model is registered with `django-auditlog` (fields: `agenda_item`, `author`, `meeting_group`, `as_group`, `body`) and with `history_log` (scoped to the organisation via `agenda_item__meeting__organisation`).

## Permissions (rules.py)

The ADD permission guard is checked against the `AgendaItem`, not the post itself:

| Permission | Who can |
|---|---|
| `discussion.add_discussionpost` | Moderators (regardless of block/private); or Discussers when agenda item is not archived, not private, and discussion is not blocked |
| `discussion.change_discussionpost` | Moderators only, meeting not archived |
| `discussion.delete_discussionpost` | Moderators or the post's author, meeting not archived |

Archived meetings revoke all three permissions for everyone including moderators. `block_discussion` on an agenda item blocks add for non-moderators but not for moderators.

## REST API

### DiscussionPostViewSet (`discussion-posts/`)

Standard DRF `ModelViewSet` with `VerboseAutoPermissionViewSetMixin`.

- `list` always returns an empty queryset — posts are delivered via WebSocket on channel subscription, not via polling.
- `retrieve` / `update` / `delete` filter the queryset to items the requesting user can see: moderators see all items including those under private agenda items; others see items under non-private agenda items only.
- `create` uses `DiscussionPostCreateSerializer`; the ADD permission is validated inside the serializer via `validate_model_add` rather than in the viewset, so `permission_type_map` maps `"create"` to `None`.

### ExportDiscussionPostsViewSet (`export-discussion-posts/`)

Moderator-only. The queryset is `Meeting` objects (not posts) — the caller passes a meeting PK and gets all posts for that meeting.

| Action | Method | URL | Notes |
|---|---|---|---|
| `csv` | GET | `export-discussion-posts/{pk}/csv/` | Returns `text/csv`; 404 if no posts |
| `json` | GET | `export-discussion-posts/{pk}/json/` | Returns JSON attachment; always 200 even if empty |

Export fields: `created`, `body`, `userid` (author username), `agenda_item`, `group_title`, `group_id`, `tags` (comma-joined), `pk`, `author`, `meeting_group`, `as_group`. Order: `agenda_item__order`, then `created`.

## Serializers

- `DiscussionPostDetailSerializer` — used for read operations and WebSocket payloads. No request context required (safe to use in signal handlers).
- `DiscussionPostCreateSerializer` — used for `POST`. Includes `ValidateGroupAIContext` validator that checks the meeting group belongs to the correct meeting and that the user is a group member (unless moderator). Also validates that `as_group` is only set when the group has `post_as` enabled.
- `DiscussionPostExportSerializer` — adds `userid`, `group_title`, `group_id` flat fields via `ExportBaseSerializerMixin`.

## WebSocket messages (messages.py / signals.py)

All three messages extend base classes from `voteit.messaging.base`:

| Message name | Trigger |
|---|---|
| `discussion_post.added` | `post_save` when `created=True` |
| `discussion_post.changed` | `post_save` when `created=False` |
| `discussion_post.deleted` | `pre_delete` |

All messages are published synchronously (`ch.sync_publish`) to `AgendaItemChannel` for the post's agenda item.

On `AgendaItemChannel` subscription (`channel_subscribed` signal), existing posts are bundled into a `Batch(t="discussion_post.added")` message and appended to `app_state` for efficient initial load.

The `@disable_on_raw_save` decorator on `discussion_post_change` suppresses broadcasts during data migrations (raw saves).

## Cross-app interactions

- **`voteit.agenda.signals`**: `post_save` and `post_delete` on `DiscussionPost` also trigger `maybe_mark_related_modified` / `revert_to_last_related_modified` on the parent `AgendaItem` — this updates the `related_modified` timestamp used by the frontend "unread" indicator.
- **`voteit.reactions`**: `DiscussionPost` inherits `Reactable` (a `GenericRelation` to `Reaction`), making posts eligible for emoji reactions.
- **`voteit.export_import`**: `DiscussionPost` is imported/exported as `DiscussionPostData` Pydantic schemas.

## Non-obvious design decisions

### list endpoint always returns empty

`DiscussionPostViewSet.get_queryset()` returns `DiscussionPost.objects.none()` for the `list` action. This is intentional: the frontend receives all posts via the WebSocket `app_state` batch on channel subscription. The REST list endpoint exists only to satisfy DRF's router conventions; it is never used for data retrieval.

### ADD permission is checked against AgendaItem, not DiscussionPost

`rules.py` registers the ADD predicate with `DiscussionPost.get_perm(PERM.ADD)`, but the actual permission check in `DiscussionPostCreateSerializer.validate_agenda_item` calls `validate_model_add(self, DiscussionPost, value)` where `value` is the `AgendaItem` instance. This is by design — the relevant guards (`ai_not_private`, `ai_discussion_not_blocked`, `ai_not_archived`) are all properties of the agenda item, not of a not-yet-existing post.

### as_group auto-cleared on save

`DiscussionPost.save()` sets `as_group = False` when `meeting_group_id` is absent. This prevents orphan `as_group=True` records if `meeting_group` is removed without explicitly clearing the flag.

### Export field ordering is computed at import time

`DiscussionPostExportSerializer`'s field list `_export_fields` is built once at module import by iterating `ExportBaseSerializerMixin.Meta.fields` and `DiscussionPostDetailSerializer.Meta.fields`, deduplicating while keeping a fixed prefix of `["created", "body", "userid", "agenda_item"]`. The temporary list is deleted with `del _export_fields` after the class is defined to avoid polluting the module namespace.
