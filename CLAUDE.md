# CLAUDE.md

## What This Project Is

VoteIT is a Django-based backend for online democratic decision-making. It supports meetings, voting, proposals, discussions, and speaker queues for organisations running general assemblies or async decision processes. The frontend is a separate SPA that communicates via REST and WebSocket — this repo is pure backend.

## Commands

All commands assume the virtualenv is active. Use `uv sync` to install dependencies (creates `.venv`).

```bash
# Dev infrastructure (postgres + redis only)
docker compose up -d

# Full dev start
make up          # docker compose + rqworker + runserver

# Run dev server only
make run         # python -W once manage.py runserver

# Tests
make test        # python manage.py test voteit --keepdb --failfast
make test-deps   # tests for src/ packages (voteit_org, member_dialects)
make coverage    # coverage run + report

# Run a single test module
python manage.py test voteit.poll.tests --keepdb --failfast

# Linting
ruff check voteit/ src/

# Migrations
make migrations  # makemigrations
make migrate     # migrate

# Background worker (dev)
make rqworker

# Build wheels (voteit + voteit_org + member_dialects)
make build
```

Settings module for dev: `DJANGO_SETTINGS_MODULE=project.settings_development` (auto-loaded via `.env`). Copy `.env.tpl` to `.env` for local setup.

## Architecture

### Multi-tenancy

Every resource belongs to an `Organisation`. The `Organisation.host` field maps a hostname to a tenant. The hierarchy is: **Organisation → Meeting → AgendaItem → Proposal / Poll / DiscussionPost**.

Abstract base classes enforce consistent context properties across all models:
- `OrganisationContext` → `.organisation`
- `MeetingContext` → `.organisation`, `.meeting`
- `AgendaItemContext` → `.organisation`, `.meeting`, `.agenda_item`

### Role & Permission System

- **Roles** (`voteit/core/role.py`): named singletons with optional requirements (e.g. Moderator requires Participant). Stored as a PostgreSQL `ArrayField` via `RolesField` on `Roles` abstract model.
- **Meeting roles**: `pa` (Participant), `mo` (Moderator), `pv` (Potential voter), `di` (Discusser), `pr` (Proposer).
- **Org roles**: `org_manager`, `meeting_creator`.
- **Object-level permissions**: Use the `rules` library. Each app has a `rules.py`. Permission constants are defined in `voteit.core.PERM`.

### State Machines

`python-statemachine` is used on most models. State machine classes follow the pattern `*StateMachine` (e.g. `MeetingStateMachine`, `PollStateMachine`, `ProposalStateMachine`) and live in each app's `statemachines.py`. They subclass `StateChart` and mix in `TransitionSignalMixin`. Models bind to their machine via `voteit.core.statemachines.StateMachineModelMixin` (accessed as `instance.sm`, built lazily on first access — the upstream `MachineMixin` built one inside every `Model.__init__`). Transitions are `Event` objects with `validators` for permission and condition guards. The REST layer exposes a `POST /{id}/event/` endpoint via `StateMachineMixin`.

### REST API

DRF with a central router at `voteit/core/rest_api/router.py`. Apps register ViewSets with `@router.register(...)`. All endpoints live under `/api/`. Auth: Token + Session.

### WebSocket / Real-time

Django Channels at `ws/`, using the `chanx` library. One consumer for the whole app:
`voteit/messaging/consumer.py`. Wire format is `{"action": ..., "payload": ...}`.

The socket is **push-only** apart from subscription control (`channel.subscribe`,
`channel.leave`, `channel.list_subscriptions`) and `s.ping` — every app-level incoming
message was migrated to REST.

- `voteit/*/channels.py` declares `ContextChannel` subclasses: a channel-layer group
  (`"<name>_<pk>"`) plus the object and permission that decide who may subscribe.
  A meeting has two, `participants` and `moderators`, and a client subscribes to
  exactly one. They partition the audience, so anything meeting-wide goes out with
  `voteit.meeting.channels.broadcast_meeting`, which publishes to both. (There is no
  `meeting` channel; it shared `participants`' permission and only cost clients a
  second subscribe and a second app state snapshot.)
- `voteit/*/messages.py` declares outgoing messages — `chanx` `BaseMessage` subclasses
  with a `Literal` action and a pydantic payload, registered with `@outgoing`. There is
  no `*.added`; the client upserts on `*.changed`.
- Each outgoing type also gets a generated `<action>.batch` sibling. Runs of the same
  message to the same target within one transaction collapse into one batch on commit
  (`voteit/messaging/utils.py::TransactionBatcher`, threshold `VOTEIT_BATCH_THRESHOLD`).
- Subscribing is deferred to RQ. The worker streams `channel.subscribed` (naming the
  collectors that will contribute), then the initial state as `channel.state` bundles
  built by the named, ordered collectors in `voteit/*/collectors.py`, then
  `channel.state_complete`.
- Connection rows live in `voteit/messaging/models.py`; `code` is null while open.
- RQ queues: `default`, `long`.
- `/asyncapi/docs/` (DEBUG only) publishes the full message schema.

### Registry Pattern

A `Registry` (typed dict, `voteit/core/component.py`) is used for: poll methods, electoral register policies, proposal ID policies, vote transfer policies, meeting dialects, pluggable components, content types, predicates.

### Dialects

YAML-based meeting configuration profiles loaded from `src/dialect_configs/dialects/` (dev) or `BASE_DIR/dialects` (prod). Applied to a meeting to configure voting behaviour, roles, and group structures without code changes.

### Components

Pluggable per-meeting or per-org features (`MeetingComponent`, `OrganisationComponent`) with `on`/`off` state via a plain `enabled` BooleanField. Registered in `meeting_components` / `organisation_components` registries.

### Notable Conventions

- **Narrative docs as doctests**: `docs/narrative.md` and `docs/workflows.md` are runnable as doctests, asserted in each app's `test_docs.py`. These serve as integration-level documentation and must stay passing.
- **Auditlog context**: All models using `django-auditlog` implement `get_additional_data()` returning `{o, m, ai}` context keys.
- **Pydantic v2** is used for schemas/validation.
- **Test runner**: Django's built-in `manage.py test`, not pytest. Coverage via the `coverage` package.
- **Package manager**: `uv` with `uv.lock`. Do not use pip or poetry.
- **Linting**: `ruff` only (includes isort with `force-single-line = true`).

### Key Packages in `src/`

Local editable sub-packages (separate git repos, mounted via uv workspace):
- `src/voteit_org/` — org-level membership and REST features
- `src/member_dialects/` — voting behaviour plugins
- `src/dialect_configs/` — YAML dialect configuration files
