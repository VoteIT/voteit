# Contributing to VoteIT

Thank you for your interest in contributing. This guide covers everything you need to get productive: setting up your environment, understanding the codebase conventions, and getting a change accepted.

---

## Table of contents

1. [Development environment](#development-environment)
2. [Running the tests](#running-the-tests)
3. [Code style](#code-style)
4. [Architecture primer](#architecture-primer)
5. [Adding a new feature](#adding-a-new-feature)
6. [Pull request process](#pull-request-process)

---

## Development environment

See [README.md](README.md#quick-start) for the full setup walkthrough. In short:

```bash
uv sync
cp .env.tpl .env
docker compose up
uv run python manage.py migrate
make up
```

Install pre-commit hooks so the basic hygiene checks run locally before you push:

```bash
uv run pre-commit install
```

---

## Running the tests

```bash
# Full test suite (uses --keepdb to skip re-creating the DB each run)
make test

# Workspace packages (voteit_org, member_dialects)
make test-deps

# A single app
uv run python manage.py test voteit.poll.tests --keepdb --failfast

# With coverage
make coverage
```

The project uses Django's built-in `manage.py test` runner — not pytest. Tests use the standard `django.test.TestCase` and `rest_framework.test.APITestCase`.

### Fixtures

A shared fixture provides the base data most tests need:

```python
class MyTest(TestCase):
    fixtures = ["meeting_test_fixture"]
```

This fixture (`voteit/core/fixtures/meeting_test_fixture.yaml`) creates one organisation, one meeting, and three users: `moderator`, `participant`, and `org_manager`. Load it in any test that needs a realistic starting state.

### Testing utilities

`voteit/core/testing.py` has several helpers worth knowing:

- `run_permission_tests(view, cases)` — runs a list of `(user, expected_status)` pairs against a view, so permission matrix tests stay concise.

### Narrative doctests

`docs/narrative.md` and `docs/workflows.md` are executed as doctests by each app's `test_docs.py`. If you change model behaviour or permission logic, check whether the narrative docs need updating too.

---

## Code style

Linting is enforced with **ruff** (replaces flake8, isort, and more).

```bash
# Check
uv run ruff check voteit/ src/

# Auto-fix safe issues
uv run ruff check --fix voteit/ src/

# Format
uv run ruff format voteit/ src/
```

Key rules to keep in mind:

- **Imports**: one import per line (`force-single-line = true` in ruff config). Always group standard library → third-party → local.
- **Type annotations**: use `from __future__ import annotations` at the top of every file and keep annotations on new code. Use `TYPE_CHECKING` guards for imports that are only needed at type-check time.
- **Docstrings**: add at least a one-line docstring to every new model class, complex method, or non-obvious utility function.
- **Comments**: leave a brief comment whenever you use a pattern that isn't self-explanatory — late imports for circular dependencies, `objects.none()` returns in ViewSets, dynamic class dispatch, etc.

---

## Architecture primer

VoteIT has several framework-level patterns that appear everywhere. Understanding them upfront saves a lot of time.

### Object hierarchy

```
Organisation → Meeting → AgendaItem → Proposal / Poll / DiscussionPost
```

Abstract base classes enforce this:

| Mixin                 | Properties provided                   |
| --------------------- | ------------------------------------- |
| `OrganisationContext` | `.organisation`                       |
| `MeetingContext`      | `.meeting`                |
| `AgendaItemContext`   | `.agenda_item` |

### State machines (django-fsm)

Most domain models have a `state` field managed by `django-fsm`. Transitions are defined as methods decorated with `@transition`. Valid state combinations across the hierarchy are documented in [docs/workflows.md](docs/workflows.md).

```python
@transition(field="state", source="upcoming", target="ongoing")
def publish(self, by=None):
    ...
```

### Permissions (django-rules)

Object-level permissions are declared in each app's `rules.py` using predicate functions:

```python
@predicate
def is_author(user, obj):
    return obj.author == user

rules.add_perm("proposal.change_proposal", is_author | is_moderator)
```

Permission constants live in `voteit.core.PERM`. String permission names follow the pattern `"<app>.<perm>_<model>"`, built with `Model.get_perm(PERM.CHANGE)`.

ViewSets use `VerboseAutoPermissionViewSetMixin` which maps DRF actions to rules checks automatically. In `DEBUG` mode it includes the failing predicate name in the error response, which is useful when writing new rules.

### REST API registration

ViewSets register themselves with the central router via a decorator:

```python
from voteit.core.rest_api.router import router

@router.register("proposals", basename="proposal")
class ProposalViewSet(VerboseAutoPermissionViewSetMixin, ModelViewSet):
    ...
```

The decorator is picked up when the app's `AppConfig.ready()` imports the views module. You never need to touch `project/urls.py`.

### WebSocket messages

Real-time events are broadcast via `channels.py` in each app. Each app defines a `ContextChannel` subclass and a set of message classes. Messages are sent from signals or view actions, not from model `save()` methods.

### Workspace packages (`src/`)

`src/voteit_org/` and `src/member_dialects/` are separate Python packages managed as a `uv` workspace. They depend on the main `voteit` package. Run `make test-deps` to test them. If you need a new electoral register policy, add it to `member_dialects`.

---

## Adding a new feature

A typical feature touching a new domain object involves these files (using `myapp` as a placeholder):

```
voteit/myapp/
  __init__.py
  apps.py          # AppConfig — import rules and REST views in ready()
  models.py        # Model inheriting from the right context mixin
  rules.py         # Permission predicates and rules.add_perm() calls
  workflows.py     # FSM state + transitions (if the model has a lifecycle)
  signals.py       # Django signals, WebSocket broadcasts
  channels.py      # ContextChannel subclass for WS push (if needed)
  messages.py      # Envelope message classes for WS events (if needed)
  admin.py         # Django admin registration
  rest_api/
    serializers.py
    views.py        # ViewSet with @router.register decorator
    tests/
      test_views.py
      test_serializers.py
  tests/
    test_models.py
    test_rules.py
  migrations/
```

Add the app to `INSTALLED_APPS` in `voteit/settings_tpl.py`.

### Checklist for a new model

- [ ] Inherits from the correct context mixin (`AgendaItemContext`, etc.)
- [ ] Has `get_additional_data()` for the auditlog (returning `{o, m, ai}`)
- [ ] Decorated with `@auditlog.register()`
- [ ] Has at least one test for each unique constraint
- [ ] Permissions defined in `rules.py` and tested in `test_rules.py`

---

## Pull request process

1. **Branch** from `main`. Use a descriptive branch name (`feat/electoral-weight`, `fix/poll-checksum`).
2. **Keep PRs focused.** One logical change per PR makes review faster and reverts cleaner.
3. **Tests must pass.** `make test` and `make test-deps` should both be green before you open a PR.
4. **Lint must pass.** Run `uv run ruff check voteit/ src/` and fix any issues.
5. **Update [docs/narrative.md](docs/narrative.md) or [docs/workflows.md](docs/workflows.md)** if your change affects model relationships, permissions, or state machines. These files are part of the test suite.
6. **Add a CHANGELOG entry** under the appropriate version heading in [CHANGELOG.md](CHANGELOG.md).
7. **Open the PR** against `main`. A maintainer will review and may request changes.
