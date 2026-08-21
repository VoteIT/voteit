# VoteIT 4

VoteIT is a Django-based backend for online democratic decision-making. It powers meetings, voting, proposals, discussion threads, and speaker queues for organisations running general assemblies or asynchronous decision processes.

The frontend is a separate single-page application that communicates with this backend over REST and WebSocket — see [voteit_frontend](https://github.com/VoteIT/voteit_frontend). This repository is pure backend.

---

## Features

- **Meeting lifecycle** — Upcoming, ongoing, closed, and archived states with fine-grained moderator control.
- **Proposals** — Create, publish, retract, and version proposals with diff tracking.
- **Voting / Polls** — Pluggable poll methods (STV, approval, simple majority, …). Full electoral register support with configurable voter weight and delegation policies.
- **Speaker queues** — Ordered speaker lists with presentation-mode support.
- **Discussions** — Threaded discussion posts tied to agenda items.
- **Real-time updates** — WebSocket push via Django Channels and the `chanx` protocol.
- **Role-based access** — Per-meeting roles (Moderator, Participant, Voter, …) with object-level permission rules.
- **Multi-tenancy** — Every resource belongs to an `Organisation`; hostname routing maps tenants automatically.
- **Token API** — Meeting-scoped API keys for programmatic or integration access.
- **Audit log** — Full change history on all domain models.

---

## Technology stack

| Layer           | Technology                                 |
| --------------- | ------------------------------------------ |
| Framework       | Django 5.2+, Django REST Framework         |
| Database        | PostgreSQL (psycopg3)                      |
| Real-time       | Django Channels 4, Redis                   |
| Background jobs | RQ + RQ Scheduler                          |
| Auth            | Token auth, Session auth, OAuth2 (IDProxy) |
| Permissions     | `django-rules` (object-level predicates)   |
| State machines  | `python-statemachine`                      |
| Validation      | Pydantic v2                                |
| Package manager | `uv`                                       |

---

## Quick start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Docker (for Postgres and Redis)

### Setup

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd voteit

# 2. Copy the environment template and fill in any secrets
cp .env.tpl .env

# 3. Install Python dependencies (creates .venv automatically)
uv sync

# 4. Start Postgres and Redis
docker compose up

# 5. Apply migrations
uv run python manage.py migrate

# 6. Create a superuser
uv run python manage.py createsuperuser

# 7. Start everything (Django dev server + RQ worker)
make up
```

The API is now available at `http://localhost:8000/api/`.
The Django admin is at `http://localhost:8000/admin/`.

---

## Repository layout

```
voteit/               Main Django project package
  core/               Shared base models, permissions, REST router, signals
  meeting/            Meeting model and lifecycle
  agenda/             Agenda items
  proposal/           Proposals (including diff proposals)
  poll/               Polls and voting
  discussion/         Discussion posts
  speaker/            Speaker queues
  organisation/       Organisations and org-level roles
  token_api/          Meeting-scoped token API
  …                   Additional feature apps (reactions, presence, stats, …)

src/
  voteit_org/         Organisation membership and REST features (workspace package)
  member_dialects/    Electoral register policy plugins (workspace package)
  dialect_configs/    YAML meeting configuration profiles

project/              Django project settings and URL configuration
docs/                 Narrative docs (also run as doctests) and workflow tables
```

See [CLAUDE.md](CLAUDE.md) for a detailed architecture description including the role and permission system, state machine conventions, and registry patterns.

---

## Common commands

```bash
make up            # Start docker services + RQ worker + dev server
make down          # Stop docker services

make test          # Run the full test suite (--keepdb --failfast)
make test-deps     # Run tests for src/ workspace packages
make coverage      # Run tests with coverage report

make migrations    # makemigrations
make migrate       # migrate

make rqworker      # Start background worker only
```

All commands assume the virtualenv is active. If using `uv run`, prefix with `uv run` instead of activating.

---

## Documentation

| Document                               | Contents                                                  |
| -------------------------------------- | --------------------------------------------------------- |
| [CLAUDE.md](CLAUDE.md)                 | Architecture guide, conventions, and key patterns         |
| [docs/narrative.md](docs/narrative.md) | Model relationships and permission rules (also a doctest) |
| [docs/workflows.md](docs/workflows.md) | Valid state machine combinations across models            |
| [INSTALL.md](INSTALL.md)               | Minimal installation notes                                |
| [CHANGELOG.md](CHANGELOG.md)           | Release history                                           |
| [CONTRIBUTING.md](CONTRIBUTING.md)     | How to contribute                                         |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)

VoteIT is licensed under the [GNU Affero General Public License v3.0 or later](LICENSE).
