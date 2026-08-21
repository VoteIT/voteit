# voteit.components

Provides a pluggable feature-flag system for meetings and organisations. A component is a named, database-persisted record that can be switched on or off and carries optional typed settings. Other apps register their features here so moderators (or dialect installers) can enable them on demand without code changes.

## Models

Both concrete models inherit from the abstract `Component` base (defined in `abcs.py`).

**`MeetingComponent`** — a feature attached to a meeting. FK to `Meeting`; accessed as `meeting.components`.

**`OrganisationComponent`** — a feature attached to an organisation. FK to `Organisation`; accessed as `organisation.components`.

Shared fields on both:
- `component_name` — matches a key in the relevant registry; max 30 chars.
- `enabled` — plain `BooleanField(default=False)`. Not a state machine.
- `settings_data` — nullable `JSONField`; raw storage for Pydantic-validated settings.

Both models are registered with `django-auditlog` tracking `component_name`, `settings_data`, `enabled`, and their parent FK.

## Abstract base classes (`abcs.py`)

### `Component`

Abstract model base for `MeetingComponent` and `OrganisationComponent`. Key behaviour:

- `adapter` — `cached_property` that looks up `component_name` in the registry returned by `get_registry()`. Returns `None` (silently) if the name is not registered.
- `adapted` — instantiates and returns the adapter: `self.adapter(self)`.
- `is_valid` — `True` if the adapter exists and either has no schema or the stored `settings_data` validates against it.
- `settings` property — reads `settings_data` and returns a hydrated Pydantic model, or `None` if invalid. The setter accepts a `dict` or a schema instance; it validates and stores the dumped model.
- `enable()` — calls `valid_component_name()` and `valid_settings()` and raises `ValueError` if either fails; then sets `enabled = True`. Does not save.
- `disable()` — sets `enabled = False`. No validation. Does not save.

Subclasses must implement `get_registry()` to return the appropriate `Registry`.

### `ComponentAdapter`

Abstract class that plugin authors subclass to define a component type. Class-level attributes:

- `name` — unique string key used as the registry key and stored in `component_name`.
- `title` — human-readable label.
- `schema: type[BaseModel] | None = None` — optional Pydantic model for settings validation. If `None`, the component has no configurable data. The JSON Schema exposed over REST is pydantic v2 output: draft 2020-12, `$defs` rather than `definitions`, `anyOf` for optional fields.
- `disable_on_close: bool = False` — if `True`, the component is automatically disabled when its meeting transitions to the `closed` state.

The constructor receives the `Component` instance as `self.component`.

## Registries (`registries.py`)

```python
meeting_components = Registry(ComponentAdapter)
organisation_components = Registry(ComponentAdapter)
```

Adapter classes self-register using the registry as a decorator:

```python
@meeting_components
class ProposalPrint(ComponentAdapter):
    name = "proposal_print"
    ...
```

A class can be registered in both registries by stacking decorators (see `FlashMessage`). The `Registry.__call__` uses the class's `name` attribute as the key.

Registration is triggered at app startup via `ComponentsConfig.ready()` → `register()` in `app/components/__init__.py`, which imports all adapter modules.

## Built-in adapters (`app/components/`)

| Adapter class | Registry | Schema | `disable_on_close` | Notes |
|---|---|---|---|---|
| `FlashMessage` | both | `MessageSchema` (`msg`, `type`) | `False` | Announcement banner; `type` defaults to `"info"` |
| `ProposalPrint` | meeting | none | `False` | Enables print view for proposals |
| `RepeatedIRV` | organisation | none | `False` | Enables repeated IRV election mode |
| `DialectsFilter` | organisation | `DialectsFilterSchema` (`include`, `exclude`) | `False` | Restricts which dialects are installable in meetings; validates names against `get_named_paths()` |

`ActiveUsersComponent` and `PresenceComponent` live in their respective apps but are registered in `meeting_components` with `disable_on_close = True`.

## REST API

### `MeetingComponentViewSet` — `meeting-components/`

Registered at `meeting-components/`. Only `MeetingComponent` has a dedicated ViewSet; `OrganisationComponent` is surfaced read-only through the organisation serializer.

| Action | Method | URL | Serializer | Notes |
|---|---|---|---|---|
| `list` | GET | `meeting-components/` | `MeetingComponentSerializer` | Filtered by `?meeting=<pk>`; queryset scoped to meetings where the user is a participant |
| `create` | POST | `meeting-components/` | `CreateMeetingComponentSerializer` | Permission check done in serializer (`validate_model_add`); no viewset-level ADD permission |
| `retrieve` | GET | `meeting-components/{pk}/` | `VerboseMeetingComponentSerializer` | Returns extra `schema` field (JSON Schema from Pydantic); no viewset-level VIEW permission |
| `partial_update` | PATCH | `meeting-components/{pk}/` | `MeetingComponentSerializer` | Requires `meeting_not_archived & is_moderator`; `component_name` and `meeting` are read-only |
| `destroy` | DELETE | `meeting-components/{pk}/` | — | Requires `meeting_not_archived & is_moderator` |

`create` uses `CreateMeetingComponentSerializer` which enforces: name must be in the registry, and only one instance of each `component_name` is allowed per meeting.

`permission_type_map` overrides `create` and `retrieve` to `None` — those actions skip the automatic permission lookup and rely on serializer-level and queryset-level access control instead.

### Organisation components

`OrganisationComponent` records are embedded in the `Organisation` REST response as the `components` field. Only enabled, valid components are included (filtered via `Organisation.enabled_components()`). There is no separate CRUD endpoint for `OrganisationComponent`.

## WebSocket messages (`messages.py`)

All are outgoing-only, published to `MeetingChannel`:

- **`meeting_component.changed`** (`MeetingComponentChanged`) — new or updated valid component, and the channel subscribe initial state. There is no `.added`; the client upserts.
- **`meeting_component.changed`** (`MeetingComponentChanged`) — component updated and still valid.
- **`meeting_component.deleted`** (`MeetingComponentDeleted`) — component deleted, or updated but now invalid/disabled so the frontend should remove it from its data layer.

`OrganisationComponentChanged/Deleted` are defined but currently unused (no signal wires them).

## Signals (`signals.py`)

- `channel_subscribed` on `MeetingChannel` — pushes `MeetingComponentChanged` for every component where `is_valid` is `True`, regardless of `enabled`. The frontend uses this to populate its data layer for all components, including disabled ones.
- `post_save` on `MeetingComponent` (deferred to transaction commit) — publishes `MeetingComponentChanged` if valid, otherwise `MeetingComponentDeleted` (telling the frontend to drop the record).
- `pre_delete` on `MeetingComponent` — publishes `MeetingComponentDeleted` immediately (before the row is gone).
- `after_sm_transition` on `Meeting` — when the meeting enters `closed`, iterates all adapters with `disable_on_close = True`, finds enabled components with those names, calls `component.disable()` and saves.

## Permissions (`rules.py`)

Only `MeetingComponent` permissions are defined here. All three require `meeting_not_archived & is_moderator`:

| Permission | Guard |
|---|---|
| `MeetingComponent.ADD` | `meeting_not_archived & is_moderator` |
| `MeetingComponent.CHANGE` | `meeting_not_archived & is_moderator` |
| `MeetingComponent.DELETE` | `meeting_not_archived & is_moderator` |

No permissions are defined for `OrganisationComponent` — management happens outside this app.

## Notable design decisions

**`enabled` is a plain boolean, not a state machine.** The `enable()` and `disable()` methods validate preconditions but the field is set directly. This is intentional; the previous state-machine approach (migration `0002` replaced `state` with `enabled`) was removed as unnecessary complexity.

**Invalid components publish `MeetingComponentDeleted`, not `MeetingComponentChanged`.** When a save makes a component invalid (e.g. bad settings), the signal sends a delete message so the frontend removes the record from its local state. This keeps the frontend data layer consistent without a separate "invalid" state.

**`adapter` is a `cached_property`.** After the first lookup the adapter class is cached on the instance. If the registry changes at runtime (unusual outside tests) the old value stays. Call `del instance.adapter` to bust the cache.

**`component_name` and `meeting` are read-only on update.** `MeetingComponentSerializer.Meta.read_only_fields` locks both. PATCH requests that include these fields silently ignore them, as verified by the test `test_patch_moderator`.

**Enabling with settings in the same request is allowed.** The `ComponentSerializer.validate()` cross-field check skips the existing-settings check if `settings` is also in the incoming `attrs`, allowing a single PATCH to set settings and flip `enabled = True` atomically.

**Only one instance per component name per meeting.** `CreateMeetingComponentSerializer.validate_component_name` enforces this. There is a `multiple` attribute on some adapters (`FlashMessage.multiple = True`) but it is not yet enforced by the system — noted as "Not implemented yet" in `ComponentAdapter`.

## Tests

```bash
python manage.py test voteit.components --keepdb --failfast
```

- `tests/test_models.py` — `enable()`/`disable()` validation, schema-less components.
- `tests/test_rules.py` — permission assertions for moderator/participant/anonymous and archived meetings.
- `tests/test_signals.py` — WebSocket message assertions for all CRUD events, `disable_on_close` behaviour.
- `rest_api/tests/test_serializers.py` — serializer validation, bad data, enable-with-settings-in-same-request.
- `rest_api/tests/test_views.py` — full endpoint coverage for `MeetingComponentViewSet` and the embedded organisation component in the organisation endpoint.
