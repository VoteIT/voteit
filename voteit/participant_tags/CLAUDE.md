# voteit.participant_tags

Stores per-user, per-meeting metadata tags (e.g. gender identity, pronouns) so that moderators and the frontend can display demographic breakdowns or pronouns alongside participants. Tags are optional, participant-controlled, and gated behind meeting components that define which namespaces and allowed values exist.

## Models

### ParticipantTags (`models.py`)

One record per `(user, meeting)` pair (enforced by `unique_together`). Inherits from `MeetingContext` (which includes `AuditLogMixin`).

Fields:
- `user` — FK to `AUTH_USER_MODEL` (CASCADE); related name `"meeting_tags"`.
- `meeting` — FK to `Meeting` (CASCADE); related name `"participant_tags"`.
- `tags` — `JSONField(default=dict)`. Keys are namespace strings (e.g. `"gen"`, `"pron"`); values are either a single string or a list of strings depending on whether the namespace's component has `many=True`.

There is no state machine and no `rules.py` — access control is enforced entirely at the viewset queryset level.

## Components (`components.py`)

Tag namespaces are defined as meeting components that subclass `NamespacedTags(ComponentAdapter, ABC)`.

`NamespacedTags` carries:
- `schema = TagSettings` — Pydantic model requiring a non-empty list of unique `tags` and `many: bool = False`.
- `namespace` — abstract class attribute; the short string key used as the JSON dict key in `ParticipantTags.tags`.

Tag values are validated against `tag_format = re.compile(r"^[a-z0-9_\-]{1,20}$")` — lowercase ASCII/digits/hyphens/underscores, 1–20 chars.

Two concrete adapters are registered in `meeting_components`:

| Class | `name` | `namespace` | Title |
|---|---|---|---|
| `GenderTags` | `"gtags"` | `"gen"` | Gender |
| `PronounTags` | `"ptags"` | `"pron"` | Pronoun |

A component's `settings_data` must contain `tags` (list of allowed values) and optionally `many` (if `True`, the value is a list; otherwise a single string).

## REST API (`rest_api/views.py`)

`ParticipantTagsViewSet` registered at `ptags/`. Extends `mixins.ListModelMixin, GenericViewSet`. No `VerboseAutoPermissionViewSetMixin` — the queryset itself acts as the access gate: it returns only meetings in `upcoming` or `ongoing` state where `request.user` is a participant.

| Action | Method | URL | Notes |
|---|---|---|---|
| `list` | GET | `ptags/` | Always returns an empty list (not implemented) |
| `retrieve` | GET | `ptags/<pk>/` | Returns the current user's tags for that meeting; 404 if none exist |
| `set` | POST | `ptags/<pk>/set/` | Creates or updates tags for the current user; validates each namespace against the enabled component's allowed values |
| `remove-ns` | POST | `ptags/<pk>/remove-ns/` | Removes one or more namespaces from the tags dict; if all namespaces are removed the `ParticipantTags` record is deleted (204) |
| `destroy` | DELETE | `ptags/<pk>/` | Deletes the current user's `ParticipantTags` record |

The `set` action uses `get_or_create` so posting to a meeting where the user has no tags yet creates the record and returns `201 Created`; subsequent calls return `200 OK`.

### Serializers (`rest_api/serializers.py`)

- `SetTagsSerializer` — validates the incoming `tags` dict in two passes: first checks each value against `tag_format`, then checks each namespace against the meeting's enabled, valid component. If no enabled component exists for a namespace the request is rejected. The `update()` method only saves if something actually changed.
- `DeleteNamespaceSerializer` — accepts `ns: list[str]`; no component validation (unknown or disabled namespaces are silently ignored in the view).
- `TagsSerializer` — read-only `ModelSerializer` for `ParticipantTags`; exposes `pk`, `meeting`, `user`, `tags`.

## WebSocket messages (`messages.py`)

All messages are outgoing-only, published to `MeetingChannel`.

| Message name | Class | Payload |
|---|---|---|
| `ptags.changed` | `ParticipantTagsChanged` | `{meeting: int, user: int, tags: dict}` |
| `ptags.all` | `AllParticipantTags` | `{meeting: int, tags: {"ns:value": [user_id, ...]}}` |

## Signals (`signals.py`)

- `post_save` on `ParticipantTags` — skipped on `created=True` (tags are always updated immediately after creation, so the create-only save carries no tag data worth broadcasting); on update publishes `ParticipantTagsChanged` with the current tags to `MeetingChannel`.
- `pre_delete` on `ParticipantTags` — publishes `ParticipantTagsChanged` with `tags={}` to `MeetingChannel`, signalling removal without a separate deleted message type.
- `channel_subscribed` on `MeetingChannel` — only fires if at least one of `GenderTags` or `PronounTags` is enabled on the meeting. Queries all `ParticipantTags` for the meeting using `.values("user_id", "tags")`, flattens them into the `"ns:value" → [user_ids]` format, and appends an `AllParticipantTags` message to the `app_state`.

## Notable design decisions

**No separate `ptags.deleted` message type.** Deletion is represented as `ptags.changed` with `tags={}`. The frontend treats an empty tags dict as "this user has no tags" and removes the record from its local state. This keeps the message set minimal.

**`post_save` skips the initial `created=True` save.** The typical call pattern is `get_or_create()` followed by `save()` after setting tags. Skipping the no-tags-yet save avoids broadcasting a useless intermediate state to all meeting subscribers.

**Namespace validation requires an enabled, valid component with `is_valid=True`.** Disabling a component in between makes previously valid tags unwritable via the API. Existing tag data in the JSON field is not cleaned up when a component is disabled; the data remains but the namespace becomes unwritable and is not included in the subscription broadcast (the broadcast checks `component_enabled` before querying).

**`AllParticipantTags` flattens tags into a reverse index.** Instead of `{user_id: tags_dict}`, the subscription message sends `{"ns:value": [user_id, ...]}`. This lets the frontend look up all users with a given tag in O(1) without iterating all participant records.

**The `send_all_tags` handler has a FIXME comment.** It hardcodes the two known `NamespacedTags` adapters (`GenderTags`, `PronounTags`) for the enabled-check rather than iterating all registered `NamespacedTags` subclasses. If a third namespace is added in the future the check must be updated.

**`get_adapted_from_ns` in `utils.py` iterates all registered meeting components.** It finds a `NamespacedTags` subclass by matching `adapter.namespace == ns`, then checks the database for an enabled, valid component with that name. This works for the current two adapters but is O(n) over all registered components.

## Tests

```bash
python manage.py test voteit.participant_tags --keepdb --failfast
```

- `tests/test_models.py` — `is_valid` on component settings, duplicate `(user, meeting)` constraint.
- `tests/test_signals.py` — WebSocket message emission on save/delete, `AllParticipantTags` payload on channel subscription, correct reverse-index format.
- `tests/test_docs.py` — runs doctests defined in the `voteit.participant_tags` package (currently `TagSettings.validate_tags` doctests in `components.py`).
- `rest_api/tests/test_views.py` — full endpoint coverage: retrieve, set single/many/multiple namespaces, bad values, disabled component rejection, remove-ns partial and full delete, destroy.
