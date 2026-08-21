# voteit/stats

Read-only reporting module that aggregates daily usage statistics per organisation and exposes them via Django admin dashboards. No REST API — internal monitoring only.

## What it does

1. A nightly RQ job (`populate_history_log`, 04:00) aggregates the previous day's activity into one `HistoryLog` row per organisation.
2. `HistoryLog` stores counts and durations gathered from auditlog, WebSocket connections, proposals, speakers, and invitations.
3. Django admin dashboards (`controlcenter`) render trend charts and real-time widgets on top of that data.

## Core model: HistoryLog

One record per `(org, date)` — the unique constraint enforces idempotency in the job.

Key fields:

| Field | Source |
|---|---|
| `action_count` / `action_types` | `auditlog.LogEntry` |
| `user_online_count` / `online_duration` / `connection_count` | `voteit.messaging.Connection` |
| `login_count` | auditlog updates on `User` |
| `speaker_count` / `spoken_duration` | `voteit.speaker.Speaker` |
| `accepted_invitation_count` | `voteit.invites.MeetingInvite` |
| `proposal_outcomes` | `voteit.proposal.Proposal` final states |
| `content_types` | registry (see below) |

`mean_online_duration` and `mean_spoken_duration` are Django `GeneratedField`s (computed in the database).

## Background job

`jobs.py` — `populate_history_log`:

- Scheduled via `@schedule_job("0 4 * * *")`, registered in `apps.py` `ready()`.
- Skips organisations that already have a log for the target date (idempotent).
- Skips "uninteresting" days — no `LogEntry` and no `Connection` activity.
- Date range filters use `mk_daterange_filter()` which produces `__gte` / `__lt` bounds on a datetime field (avoids slow `__date` lookups on unindexed columns).
- `translate_action_keys()` converts auditlog integer action codes (0–3) to `create`/`update`/`delete`/`access` strings before storing in `action_types`.

## Registry: history_log decorator

`registry.py` exposes `@history_log(org_path)` — a class decorator that registers a model so its instances are counted under `content_types` in each org's daily log.

`org_path` is a Django ORM lookup string from the model to its organisation (e.g. `"agenda_item__meeting__organisation"`).

Add new models here when a new content type should appear in daily stats. The registry is consumed by the job; no other code reads it at runtime.

## Dashboards

`dashboards.py` — built on `controlcenter`. Two dashboard groups:

- **`LatestStats`** — 10-day rolling window: ActiveOrgs, ActiveOrgsOnline, DailyVoteChart, DailyOrgVoteChart, OnlineYesterdayChart.
- **`NowStats`** — real-time: OnlineUserChart (last 20 min), ActionsLast24 (hourly buckets).
- **`SocketStats`** — websocket connections: opened per hour, session-length distribution, close codes.

Dashboard widgets query `HistoryLog` and live `voteit.messaging.Connection` / `auditlog.LogEntry` directly — they do not go through any service layer. `SubquerySum` (from `sql_util`) is used for efficient per-org aggregations.

`Connection` has **no FK to User**, so every user- or org-scoped connection query goes through an explicit subquery (`user_id__in=User.objects.filter(...).values("pk")`) rather than a join.

## Admin

`HistoryLogAdmin` is read-only (`has_add_permission`, `has_change_permission`, `has_delete_permission` all return `False`). The custom `templates/admin/base_site.html` injects a link to `/admin/dashboard/`.

## Tests

`tests/test_jobs.py` — comprehensive coverage of the nightly job: unique constraint, connection counting, action types, speaking stats, invitations, online durations, login count, proposal outcomes, content type registry, and selective date processing.

`tests/test_dashboards.py` — verifies `DailyOrgVoteChart` aggregation and legend/series output.

Run with:

```bash
python manage.py test voteit.stats --keepdb --failfast
```

## Conventions

- Stats are **write-once via job** — never mutate `HistoryLog` rows after creation.
- All aggregation happens in SQL (annotations, subqueries) — avoid Python-side loops over querysets.
- The stats app depends on many other apps but nothing depends on stats — keep it that way.
