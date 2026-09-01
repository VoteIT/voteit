# voteit.core

The foundational app for the entire VoteIT project. It provides the abstract base classes, role and permission infrastructure, the Registry pattern, the custom User model, state machine signal integration, and shared REST API mixins that every other app depends on. No business logic lives here — only structural primitives and cross-cutting concerns.

## Abstract Base Classes (`abcs.py`)

Three context ABCs enforce a consistent interface across all models. Every model must inherit the appropriate one:

- `OrganisationContext` — anything scoped to an org; requires `.organisation` property
- `MeetingContext(AuditLogMixin, ABCModel)` — anything scoped to a meeting; requires `.meeting` property
- `AgendaItemContext(AuditLogMixin, ABCModel)` — anything scoped to an agenda item; requires `.agenda_item` property

`ABCModel` resolves the Django / `ABCMeta` metaclass conflict. Use it (or a subclass) instead of `models.Model` when you also need abstract methods.

`AuditLogMixin` is mixed into all three context classes. Its `get_additional_data()` populates audit log entries with `{o, m, ai}` keys so log entries are always context-annotated without extra queries.

`BaseContent` (`models.py`) is the shared mixin for user-authored content — it adds `body` (rich text), `author`, `created`, `modified`, `mentions` (M2M to User), and `tags` (ArrayField).

## Role System

### Role (`role.py`)

`Role` extends `str`. This is intentional: roles compare equal to plain strings, hash identically, serialize to JSON, and can be stored in sets. Each role has a `title`, optional `description`, optional `predicate` (linked predicate), and a `requires` set of other roles.

When roles have requirements, adding role X automatically adds all roles that X requires (transitive). Removing role X also removes any role whose `requires` set includes X.

### Roles model (`models.py`)

`Roles(ABCModel)` is the abstract join table between a user and a context (e.g. `MeetingRoles`). Subclasses must declare:
- `context` — FK to the context model (e.g. Meeting)
- `valid_roles` — class-level dict mapping name → Role
- `assigned` — `RolesField` (see Fields below)

Mutations go through `.add(*roles)` and `.remove(*roles)` which fire the `roles_added` / `roles_removed` signals. A `Roles` row is auto-deleted when `.assigned` becomes empty.

`Roles.save()` enforces that the user and context belong to the same organisation. Testing users with `organisation=None` are exempt.

### RoleContextMixin (`models.py`)

Abstract mixin for any model that can have roles assigned to it (Meeting, Organisation). Provides:
- `add_roles(user, *roles)` / `remove_roles(user, *roles)` — delegate to the `Roles` subclass
- `get_roles(user)` → `set[Role] | None`
- `has_roles(user, *roles)` / `has_any_roles(user, *roles)` — efficient DB-level checks
- `get_userids_with_roles(*roles)` / `get_userids_with_any_roles(*roles)` — return PKs

All methods silently return an empty result for anonymous (unauthenticated) users via the `@real_user_only` decorator.

## Custom Fields (`fields.py`)

**`RolesField`** — stores a sorted comma-separated list of role names in a single `CharField`. Reads back as `list[str]`. Validates against `valid_keys` at the field level. Used as the `assigned` column on all `Roles` subclasses.

**`RichTextField`** — a `TextField` that runs an HTML cleaner (`strict_clean_html` by default) in `pre_save`. The cleaner is configurable; `relaxed_clean_html` is available for moderator-authored content.

## User Model (`models.py`)

`User(AbstractUser)` adds:
- `organisation` — FK to Organisation (nullable only to ease testing; should never be null in production)
- `userid` — optional human-readable ID (lowercase alphanumeric + `-_`); unique per organisation
- `identity_id` — opaque string used to link accounts across organisations (e.g. for SSO)
- `img_url` — external profile image URL
- `image` — uploaded profile image (stored at `org_{org_id}/images/{uuid}.{ext}`)

`userid` uniqueness is enforced per organisation via a `UniqueConstraint`. The `UserIDValidator` restricts charset to `[a-z0-9-_]`.

On `post_save` (not on create) / `pre_delete`, an `InvalidateUserCache` WebSocket message is broadcast to the user's own `OrganisationChannel` to flush any SPA-side cache. Every socket joins that channel on connect, so it reaches everyone who could hold a cached copy. A user without an organisation publishes nothing.

## Registry Pattern (`component.py`)

`Registry(Dict[str, T])` is a typed dict that doubles as a decorator:

```python
some_registry = Registry(AbstractBase)

@some_registry
class MyConcrete(AbstractBase):
    name = "my_key"   # used as registry key; falls back to __name__.lower()

@some_registry("explicit_key")
class AnotherConcrete(AbstractBase): ...
```

Registration validates that the class is a non-abstract subclass (or instance, for object registries) of the required type. `registry.choices()` returns `[(key, title)]` pairs for use in Django choice fields.

### Registries in use (`registries.py`)

- `predicates` — `PredicateRegistry(Predicate)`: all permission predicates; populated via `@predicate` decorator
- `content_types` — `ContentRegistry(Model)`: all named Django models; populated at app startup from `class_prepared` signal; supports `get_natural_key(obj)`

## Predicate System (`predicate.py`)

`Predicate` extends `rules.Predicate` with:
- `.role` — optional back-link to a `Role` whose check this predicate implements
- `.output()` — serialisable `PredicateOutput` Pydantic schema (used by frontend tooling)
- Optional verbose logging controlled by `VERBOSE_PERMISSION_LOG` / `PERMISSON_LOG_FAIL_ONLY` settings

Use the `@predicate` decorator (from `decorators.py`) rather than `@rules.predicate`. It registers the predicate in the `predicates` registry and links it bidirectionally to a role if `role=` is supplied.

## PERM Constants (`__init__.py`)

```python
from voteit.core import PERM

PERM.VIEW          # "view"
PERM.ADD           # "add"
PERM.CHANGE        # "change"
PERM.DELETE        # "delete"
PERM.MODERATE      # "moderate"
PERM.HANDLE        # "handle"
PERM.CHANGE_ROLES  # "change_roles"
PERM.VIEW_ROLES    # "view_roles"
PERM.CHANGE_STATE  # "change_state"
PERM.ARCHIVE       # "archive"
PERM.MANAGE        # "manage"
PERM.NOT_ALLOWED   # "__not_allowed"
```

These are combined with model names by `RulesModelMixin.get_perm()` to produce full permission strings like `"meeting.moderate"`. Always reference `PERM.*` constants rather than raw strings.

## State Machine Integration (`statemachines.py`)

`TransitionSignalMixin` is mixed into every state machine class in the project. It fires Django signals around each transition:

- `before_sm_transition` — sent before a transition executes; args: `instance`, `source`, `target`, `event`
- `after_sm_transition` — sent after a transition completes; same args

State machine classes follow the naming convention `*StateMachine` and inherit from `StateChart` and `TransitionSignalMixin`. Models bind their state machine via `StateMachineModelMixin` (same module); the machine is accessible as `instance.sm`.

`StateMachineModelMixin` replaces the upstream `statemachine.mixins.MachineMixin`, which built a machine inside every `Model.__init__` — once per row of every queryset, at 209 µs / 31 kB for a `MeetingInvite` and 946 µs / 143 kB for a `Poll`, on rows that almost never read `.sm`. Here `sm` is a `cached_property`, built on first access. This is safe because every such model gives `state` a non-null default, which makes `SyncEngine.start()` an early return, and because the machine reads `state` off the model live rather than snapshotting it. `voteit/core/tests/test_statemachine.py` pins both invariants.

## Shared Rules / Predicates (`rules.py`)

Common predicates available to all apps:

- `is_author` — `instance.author == user`
- `is_author_or_group_author_member` — author check or group membership check
- `is_user` — `instance.user == user`
- `is_not_archived` — state not in archived states for meeting or agenda item
- `is_not_finished` — state not in finished states
- `is_not_private` — state is not `None` or `"private"`

## REST API Mixins (`rest_api/mixins.py`)

### `VerboseAutoPermissionViewSetMixin`

Extends `rules.contrib.rest_framework.AutoPermissionViewSetMixin`. Two additions:
1. Caches the `get_object()` result for the lifetime of a request (avoids a second DB hit when `AutoPermissionViewSetMixin.initial()` and the action handler both call `get_object()`)
2. When `VERBOSE_PERMISSIONS=True` in settings, a `PermissionDenied` response includes the specific permission string and the target object, to help with debugging

The `permission_type_map` extends the base class to mark `"metadata"` and `"transitions"` as `None` (no permission check).

### `SerializerClassesMixin`

Allows a ViewSet to declare `serializer_classes = {"action_name": SerializerClass, ...}` and fall back to `serializer_class` for unlisted actions. Transition actions return an empty `Serializer`. If `"update"` is in `serializer_classes` without `"partial_update"`, the same serializer is automatically added for `partial_update` (with a warning).

### `StateMachineMixin`

Adds one action to any ViewSet whose model uses `StateMachineModelMixin`:
- `POST|GET|PATCH /…/{id}/event/` — sends an event to the instance's state machine; wraps the call in a durable atomic transaction. `GET` returns the current state without sending anything. The browsable-API description for this action renders the machine as a mermaid diagram (`_sm_to_mermaid`).

Events are dispatched by `SMEventSerializer`, which calls `instance.sm.send(event, user=user)`.

Schema introspection is **not** on this mixin. `StateMachinesViewSet` (`rest_api/views.py`) publishes every registered machine read-only and unauthenticated at `GET /api/state-machines/` and `GET /api/state-machines/<MachineName>/`.

### `ModelContextMixin`

Helper for ViewSets that need to look up a context object (e.g. a Meeting) from request data. Subclasses declare `context_queryset` and optionally `context_lookup_kwarg` / `context_lookup_field`. Call `self.get_context(request)` inside an action.

### `SerializerClassesMixin` (serializers)

`BaseModelSerializer` validates `author` and `meeting_group` with meeting-scoped permission checks. `RichTextSerializerMixin` auto-extracts hashtags from body into `tags` and numeric `@mentions` into `mentions` (filtered to actual meeting participants).

`PydanticFieldSerializer` bridges Pydantic models and DRF JSON fields — dumps inbound Pydantic instances, passthrough for plain dicts.

## Central Router (`rest_api/router.py`)

```python
from voteit.core.rest_api.router import register

@register("my-prefix", basename="my-base")
class MyViewSet(ViewSet): ...
```

All ViewSets in the project register themselves here. The router is a `DefaultRouter` instance; its URLs are included in the root urlconf at `/api/`.

## Decorators (`decorators.py`)

| Decorator | Purpose |
|-----------|---------|
| `@predicate(role=...)` | Wrap a function as a `Predicate`, register it in the predicates registry, and optionally link it to a `Role` |
| `@on_transaction_commit` | Delay function execution until after the current DB transaction commits; runs immediately if not in an atomic block |
| `@disable_on_raw_save` | Skip signal handler when `raw=True` (e.g. during `loaddata`) |
| `@ensure_atomic` | Assert that the decorated function is called within an active atomic block |
| `@receiver_all_subclasses(signal, sender=Base)` | Connect a signal handler to all models that subclass `sender` |
| `@has_exact_filter(*names)` | Assert that a Manager method's queryset has specific exact filters applied (guards against accidental cross-tenant queries) |
| `@schedule_job(cron_string, ...)` | Schedule a function in the `long` RQ queue via `django-rq`'s scheduler |

## Signals (`signals.py`)

Custom Django signals defined here:

- `roles_added` — fired after roles are added; args: `sender` (Roles class), `instance` (Roles row), `roles` (set of Role)
- `roles_removed` — symmetric
- `before_sm_transition` / `after_sm_transition` — state machine lifecycle hooks (see State Machine Integration above)

`VoteitConsumer.post_authentication` sends a `VersionMessage` with the `BACKEND_VERSION` and `FRONTEND_VERSION` env vars to every newly connected client. (The envelope-era `consumer_connected` signal and its `send_versions` receiver are gone.)

## WebSocket Messages (`messages/`)

Three outgoing message types defined here:

- `VersionMessage` (`s.versions`) — backend + frontend version strings; sent on every WebSocket connect
- `RolesChanged` (`roles.changed`) / `RolesRemoved` (`roles.removed`) — notifies clients of role changes with `{user_pk, roles, pk, model}`. These are **deltas**, not object upserts: branch on the action pair, not on the name.
- `InvalidateUserCache` (`user.inv`) — tells the SPA to re-fetch user data after a save or delete

## Background Jobs (`jobs.py`)

`deactivate_unused_users` — runs weekly (Monday 04:35). Deactivates users who have not logged in for 30 days AND have no meeting or organisation roles. Also deletes their `UserSocialAuth` records so they can re-register via social login later.

## Managers (`managers.py`)

`AutoInheritanceManager` / `AutoInheritanceQuerySet` — wraps `model_utils.InheritanceManager` and calls `select_subclasses()` automatically on every queryset. `instance_of()` is explicitly disabled here; use a plain `InheritanceManager` if you need it.

## Request Locking (`rest_api/lock.py`)

`RequestLock` — a per-session concurrency guard backed by Django's cache. Raises `LockAlreadyRunning` (→ 409) if a matching request is already processing, or `LockCooldownActive` (→ 429) if a cooldown window is active. Acquire with `lock.acquire(request)`, always release in a `finally` block.

## REST API Filters (`rest_api/filters.py`)

`ActionAnnotatedDjangoFilterBackend` — annotates the filterset with `view_action` and `view_detail` from the view, allowing filterset classes to vary behaviour by action.

`RequiredModelChoiceFilter` — a `ModelChoiceFilter` that returns `qs.none()` if the value is empty, preventing accidental unfiltered querysets.

## Tests

```bash
python manage.py test voteit.core --keepdb --failfast
```

Doctests across all modules are run via `test_docs.py` using `load_doctests` from `testing.py`. Most utility functions, field behaviour, and the predicate/registry systems are covered by doctests in-situ.

`testing.py` exports several helpers for use across the project:

- `FakeCommit` — context manager that flushes `on_commit` hooks inside a test transaction (avoids needing `TransactionTestCase`)
- `run_permission_tests(tester, url=..., method=..., expected=[...])` — iterates a matrix of (user, expected_status) pairs, rolling back after each via savepoints
- `mk_usertag(value)` / `mk_hashtag(tag)` — produce Quill editor mention HTML for use in body field tests
- `load_doctests(tests, package)` — wires a package's doctests into Django's test loader

## Non-obvious Design Decisions

**`Role` inherits from `str`** so roles can be stored in sets, used as dict keys, compared to plain strings, and serialised to JSON without any custom handling. The downside is that `repr` and `__str__` differ — `repr` shows `Title (name)` while `str` gives the name only.

**`models_to_register` is a module-level set** (`__init__.py`). The `class_prepared` signal adds every model to it, and `CoreConfig.ready()` drains it into `content_types`. This two-phase approach avoids importing models before the app registry is ready.

**`VerboseAutoPermissionViewSetMixin` caches `get_object()`** because `AutoPermissionViewSetMixin.initial()` calls `get_object()` for permission checks before the action handler also calls it. Without the cache this causes two identical DB queries per detail request.

**`RolesField` stores data as CSV in a `CharField`** rather than a PostgreSQL `ArrayField`. This predates the project's move to Postgres and is kept for compatibility. The `assigned` field on `Roles` subclasses is the stored form; `from_db_value` unpacks it back to `list[str]` transparently.

**`@on_transaction_commit` runs immediately when not in an atomic block** (i.e. during doctests). This is intentional and documented — it makes doctests work without needing explicit transactions.

**`@ensure_atomic` is the complement** — it raises `RuntimeError` if not inside an atomic block. Use it on methods that must never run outside a transaction (e.g. ER creation).

**`has_exact_filter` guards Manager methods** against accidentally fetching rows without tenant-scoping. A manager method decorated with `@has_exact_filter("organisation")` will raise `IntegrityError` if called on a queryset that lacks an `organisation=...` filter.

**`SMEventSerializer` dispatches events by calling `instance.sm.send(event, user=user)`** rather than looking up a transition method by name. The `user` kwarg is passed through to state machine guards so permission checks inside guards have access to the requesting user.

**Content type names are explicitly declared** via the `name` class attribute on models (`name = "meeting"`, etc.). This short name is the registry key used throughout the system (predicates, signals, WebSocket messages, API payloads). If `name` is absent or `None`, it falls back to `__name__.lower()`.
