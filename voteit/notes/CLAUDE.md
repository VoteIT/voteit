# voteit.notes

Provides private per-user notes on proposals. Notes are personal and never visible to other participants — each note is tied to a specific `(user, proposal)` pair and is only ever sent to that user's own WebSocket channel. Notes are an optional meeting feature gated behind `NotesComponent`.

## Models

### Note (`models.py`)

Fields:
- `proposal` — FK to `Proposal` (CASCADE); the subject of the note. Related name `"+"` (no reverse accessor).
- `user` — FK to `AUTH_USER_MODEL` (RESTRICT); the note's owner. Related name `"notes"`.
- `meeting` — FK to `Meeting` (CASCADE); set automatically from `proposal.agenda_item.meeting` on first save. Never set directly.
- `body` — `RichTextField` using `strict_clean_html` (HTML is sanitised on save).
- `intent` — single-char choice field (`NoteIntent` enum in `__init__.py`): blank (`""`), approve (`"a"`), or deny (`"d"`).
- `created` — auto-set on creation; not editable.

Constraint: `(proposal, user)` is unique — one note per user per proposal.

### NoteIntent (`__init__.py`)

`TextChoices` enum exported from the package root:
- `BLANK = ""`
- `APPROVE = "a"`
- `DENY = "d"`

## Permissions

There is no `rules.py` in this app. Access control is enforced entirely at the queryset level: `NoteViewSet.get_queryset()` always filters to `Note.objects.filter(user=self.request.user)`, so users can only see and modify their own notes. Any attempt to access another user's note returns 404.

## REST API (`rest_api/views.py`)

`NoteViewSet` registered at `notes/`. Uses `ForceMeetingWithRoleFilter`, so `?meeting=<pk>` is required on list requests (returns 400 otherwise). The user must have any role in the specified meeting for the filter to match.

| Method | URL | Action | Notes |
|--------|-----|--------|-------|
| `GET` | `notes/?meeting=<pk>` | `list` | Only the current user's notes for that meeting |
| `POST` | `notes/` | `create` | Upsert: creates or updates the note for the given proposal; returns 201 on create, 200 on update |
| `PATCH/PUT` | `notes/<pk>/` | `update` | Standard update |
| `DELETE` | `notes/<pk>/` | `destroy` | Standard delete |
| `POST` | `notes/delete-all/` | `delete_all` | Deletes all current user's notes for the specified meeting |

### Serializers

`NoteSerializer` — used for read/update. Fields: `pk`, `agenda_item` (derived from `proposal.agenda_item`, read-only), `meeting`, `user`, `proposal`, `body`, `intent`. All fields except `body` and `intent` are read-only.

`CreateNoteSerializer` — used only on `create`. Accepts `proposal` as a writable FK. Overrides `create()` with `update_or_create(user, proposal, defaults=...)`, setting `_created` on the serializer instance so the view can return the right HTTP status.

`RelatedMeetingSerializer` — wraps `ParticipantMeetingField` (user must be a participant in the meeting); used only for the `delete-all` action.

## WebSocket (`messages.py`, `signals.py`)

All messages are outgoing-only and sent exclusively to the owning user's `UserChannel`.

| Message name | Class | Payload |
|---|---|---|
| `note.changed` | `NoteChanged` | `pk`, `proposal`, `agenda_item`, `meeting`, `user`, `body`, `intent`, `created` — the `NoteSerializer` field list, via `note_payloads` |
| `note.deleted` | `NoteDeleted` | `pk` only |

There is no `note.added`; the client upserts on `pk`.

`NoteChanged` uses `NoteAddedOrUpdatedSchema`, which extends `AddedOrUpdatedSchema` with a `created: str` field. The `created` datetime is serialised to ISO 8601 with the current timezone by the base schema validator.

### Signal handlers (`signals.py`)

- `post_save` on `Note` — deferred to transaction commit via `@on_transaction_commit`; publishes `NoteChanged` to `UserChannel(instance.user_id)`, built by the same `note_payloads` the collector uses.
- `pre_delete` on `Note` — not deferred (must fire before the row is gone); publishes `NoteDeleted` to `UserChannel(instance.user_id)`.
- `notes.notes` collector on `AgendaItemChannel` — runs when a user subscribes to an agenda item channel. `applicable()` checks `NotesComponent` is enabled for the meeting, then `collect()` queries the user's notes for that agenda item and appends them with `app_state.add_batch(NoteChanged, payloads)`, i.e. as one `note.changed.batch`. Builds the payloads with `.values()` (`note_payloads`), so it stays at two queries regardless of note count and never instantiates a Note.

## Components (`components.py`)

`NotesComponent` is a `MeetingComponent` registered in `meeting_components` under the name `"notes"`. When disabled, the collector opts out in `applicable()` and `notes.notes` is not even announced on `channel.subscribed`, but the REST API remains functional. The component gate is only checked during the initial channel subscription.

## Non-obvious design decisions

### Upsert on create
`POST notes/` is an upsert, not a strict create. If the user posts to a proposal they already have a note on, the existing note is updated in place and the response is `200 OK` instead of `201 Created`. This removes the need for the frontend to pre-check whether a note exists. The `validators = []` on `CreateNoteSerializer.Meta` suppresses the UniqueConstraint validation that would otherwise reject the request before reaching `create()`.

### meeting is auto-populated, never sent by the client
`Note.save()` derives `meeting_id` from `proposal.agenda_item.meeting_id` when `_state.adding` is True. The client never submits a meeting; neither does the serializer accept one on create. This prevents cross-meeting note injection.

### user cannot be overridden
`CreateNoteSerializer.user` is declared `read_only=True, default=CurrentUserDefault()`. A client supplying a `user` field in the POST body will have it silently ignored; the note is always created for the authenticated user. The view test explicitly verifies this.

### No rules.py / no object-level permissions
The app relies entirely on queryset scoping (`filter(user=self.request.user)`). There are no `django-rules` predicates, no `PERM` constants, and no permission checks on individual note objects. The `ModelViewSet` is used without `VerboseAutoPermissionViewSetMixin`.

### pre_delete is not deferred
The `_send_deleted` handler fires synchronously (no `@on_transaction_commit`) because it uses `pre_delete` — by the time `post_delete` would fire the `instance.user_id` is still readable, but sticking to `pre_delete` keeps the pattern consistent with other apps and avoids any risk of the instance being garbage-collected before the callback runs.

## Tests

```bash
python manage.py test voteit.notes --keepdb --failfast
```

Test modules:
- `tests/test_collectors.py` — that `note_payloads`' `.values()` output is byte-identical to `NoteSerializer`, that its field list tracks `Meta.fields`, and that the collector and the signal agree
- `tests/test_models.py` — model creation, meeting auto-population, duplicate constraint
- `tests/test_signals.py` — WebSocket message emission on add/change/delete, subscription batch, N+1 query guard on subscription
- `rest_api/tests/test_views.py` — full CRUD, upsert behaviour, HTML sanitisation, cross-user isolation, list filter enforcement, `delete-all` scoping
- `tests/test_docs.py` — runs any doctests defined in the `voteit.notes` package
