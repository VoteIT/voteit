# reactions

Allows meeting participants to attach emoji-style reactions (like, flag, etc.) to content objects (proposals, discussion posts). Each meeting defines its own set of `ReactionButton` configurations that control which roles can react, which content types are supported, and display properties. `Reaction` records are one-per-user-per-button-per-object (enforced by unique constraint), except in flag mode where a button acts as a per-object singleton regardless of user.

## Tests

```bash
python manage.py test voteit.reactions --keepdb --failfast
```

## Key files

- `models.py` — `ReactionButton` (meeting-scoped configuration), `Reaction` (the actual user action via GenericForeignKey)
- `mixins.py` — `Reactable` abstract mixin; adds `reaction_set` GenericRelation to a model
- `rules.py` — permission predicates for ADD/CHANGE/DELETE on buttons and SET/REMOVE on reactions
- `signals.py` — post_save/pre_delete handlers that broadcast WebSocket messages via `broadcast_meeting`, `AgendaItemChannel`, and `UserChannel`
- `messages.py` — outgoing WebSocket message types: `ButtonChanged`, `ButtonDeleted`, `ReactionCount`, `UserReactionChanged`, `UserReactionDeleted`
- `rest_api/views.py` — `ReactionButtonViewSet` with `set`, `remove`, `list_reactions` custom actions
- `rest_api/serializers.py` — `ButtonCreateSerializer`, `ButtonDetailSerializer`, `ReactionTargetSerializer`, `ReactionSerializer`

## Models

### ReactionButton

Configuration object scoped to a `Meeting`. Fields of note:

- `change_roles` / `list_roles` — `RolesField` (ArrayField of role strings). Controls who can react and who can see who reacted. Moderator is always implicitly included at runtime even if not stored.
- `allowed_models` — list of model shortnames (default `["proposal", "discussion_post"]`). Validated against the model registry on save.
- `flag_mode` — when `True`, the button behaves as a per-object singleton: only moderators can set/remove it, and any moderator can remove any other moderator's flag.
- `vote_template` / `on_presentation` / `on_vote` — display hints consumed by the frontend.
- `target` — optional integer hint for frontend layout (meaning is frontend-defined).
- `order` — auto-assigned on first save as the current count of buttons in the meeting.
- Uniqueness: `(meeting, title, icon, color)` case-insensitively via a `UniqueConstraint` using `Lower()`.
- `ReactionButton.save()` raises `IntegrityError` if the meeting is archived or if `allowed_models` contains an unregistered shortname, and raises `ValueError` for invalid role values.

**Manager method:** `ReactionButton.objects.counts_for_object(obj)` returns the queryset annotated with `count` — the number of reactions on `obj` per button. Useful for displaying counts without N+1 queries.

### Reaction

Represents a single user's reaction to a specific object. Uses `GenericForeignKey` (`content_type` + `object_id`). Key fields:

- `button` — FK to `ReactionButton`
- `user` — FK to user (on_delete=RESTRICT to prevent accidental deletion)
- `agenda_item` — denormalised FK to `AgendaItem` for efficient channel-level queries (nullable for legacy data)
- `meeting` — property derived from `button.meeting`

Unique constraint: `(content_type, object_id, button, user)`.

Models that want to receive reactions must inherit the `Reactable` mixin from `mixins.py`, which adds a `reaction_set` GenericRelation.

## Permissions

All permissions require the meeting to be in `upcoming` or `ongoing` state (from `meeting_upcoming_ongoing` predicate).

**ReactionButton:**

| Permission | Who |
|---|---|
| `add` | Moderator only |
| `change` | Moderator only |
| `delete` | Moderator only |
| `set` | Active button + role in `change_roles` (moderator implicit); flag buttons: moderator only |
| `remove` | Same as `set` |
| `list_reactions` | Role in `list_roles` (moderator implicit) |

**Reaction:**

| Permission | Who |
|---|---|
| `add` | Active button + role in `change_roles`; flag buttons: moderator only |
| `delete` | Active button + owner + role in `change_roles`; flag buttons: moderator only |

The `PERM_LIST_REACTIONS = "list_reactions"` constant is defined in `__init__.py` and used as a non-standard permission key.

## REST API

Registered at `/api/reaction-buttons/` via `@router.register("reaction-buttons")`.

| Method | URL | Permission | Notes |
|---|---|---|---|
| GET | `/api/reaction-buttons/` | participant in meeting | Requires `?meeting=<pk>` filter (400 without it) |
| POST | `/api/reaction-buttons/` | `add` on meeting | Creates button; uses `ButtonCreateSerializer` |
| GET | `/api/reaction-buttons/<pk>/` | participant in meeting | 404 for non-participants |
| PATCH/PUT | `/api/reaction-buttons/<pk>/` | `change` on button | Uses `ButtonDetailSerializer`; `meeting` and `flag_mode` are read-only |
| DELETE | `/api/reaction-buttons/<pk>/` | `delete` on button | |
| POST | `/api/reaction-buttons/<pk>/set/` | `set` on button | Body: `{content_type, object_id}`. Creates or retrieves reaction. Returns 201 on create, 200 if already exists. |
| POST | `/api/reaction-buttons/<pk>/remove/` | `remove` on button | Body: `{content_type, object_id}`. Idempotent: 204 even if no reaction existed. |
| POST | `/api/reaction-buttons/<pk>/list-reactions/` | `list_reactions` on button | Body: `{content_type, object_id}`. Returns `{users: [<pk>, ...]}`. |

The `content_type` field in request bodies is a model shortname string (e.g. `"proposal"`), resolved to a `ContentType` by `ReactionTargetSerializer`. The `set` action validates that the target object belongs to the same meeting as the button.

`get_queryset` filters to meetings where the requesting user is a participant, so outsiders always get 404.

## WebSocket messages

All messages are outgoing only (server → client).

**On participants/moderators subscribe:** all `ReactionButton` records for the meeting are pushed as individual `ButtonChanged` messages.

**On AgendaItemChannel subscribe:** aggregated `ReactionCount` messages (one per button+object combination with count > 0) plus one `reaction.changed.batch` covering the subscribing user's own reactions within that agenda item are pushed. This is done in exactly 2 queries regardless of the number of buttons or reactions.

That was not true until `reactions.own` stopped handing the queryset to `ReactionSerializer`. `content_type` is rendered by `ContentTypeShortnameSerializer`, a `CharField` subclass — so it gets none of DRF's pk-only optimisation for related fields and loaded a whole `ContentType` per row through the FK descriptor, which does not use `get_for_id`'s process cache. One query per reaction: 132 queries and 46 ms for the 131 reactions one user held on the busiest agenda item in the dev data. Both collectors now build payloads with `.values()` and map the pk through `collectors.content_type_shortname` (cached), which is 1 query and 0.8 ms. The mapping is mandatory, not cosmetic: `UserReactionResponseSchema.content_type` is a validated shortname, so a raw pk is rejected rather than sent.

| Message name | Type | Payload | Channel |
|---|---|---|---|
| `reaction_button.changed` | `ButtonChanged` | Full button serialization | `broadcast_meeting` |
| `reaction_button.deleted` | `ButtonDeleted` | `{pk}` | `broadcast_meeting` |
| `reaction.count` | `ReactionCount` | `{content_type, object_id, button, count}` | `AgendaItemChannel` |
| `reaction.changed` | `UserReactionChanged` | `{pk, content_type, object_id, button, user, agenda_item}` | `UserChannel` (reaction owner) |
| `reaction.deleted` | `UserReactionDeleted` | `{pk}` | `UserChannel` (reaction owner) |

`UserReactionChanged`/`UserReactionDeleted` go to the individual user's `UserChannel` rather than being responses to the REST action — this ensures all open browser tabs stay in sync.

Note `reaction.changed` is a **delta**, not an object upsert: it pairs with `reaction.deleted`, so branch on the action pair rather than on the name.

## Non-obvious design decisions

### Flag mode is a per-object singleton, not per-user
When `flag_mode=True`, the `set` view calls `get_or_create` with `defaults={"user": request.user}` — the user is placed in `defaults`, not the lookup key. This means the first moderator to flag an object creates the record and subsequent moderators get back the existing one (200). Any moderator's `remove` call deletes it regardless of who created it.

### Permission checks are against the button, not the target object
`change_roles` and `list_roles` are evaluated against the meeting, not the agenda item or the target object's current state. This is an intentional simplification: reactions do not vary by agenda item state.

### `remove` is always idempotent at the REST layer
The `remove` action deletes matching reactions and always returns 204 — it does not 404 if no reaction exists.

### DiffProposal reaction workaround
`DiffProposal` extends `Proposal` via MTI but reactions are stored against the `Proposal` content type using the `DiffProposal.pk`. A `pre_delete` signal on `DiffProposal` manually cleans up these orphaned reactions. This is tracked as a known bug (GitHub issue #340).

### `agenda_item` is denormalised on Reaction
The FK to `AgendaItem` is nullable (legacy rows may have `None`) and is set explicitly by the `set` view when creating reactions. It allows efficient channel-scoped queries without joining through the generic relation.

### Reaction count uses `pre_delete` with manual decrement
Because the count signal fires on `pre_delete` (before the row is gone), `_send_count` subtracts 1 from the live count to broadcast the post-delete value without an extra round trip.
