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
| `action_count` / `action_types` | `auditlog.LogEntry`, by `additional_data["o"]` |
| `user_online_count` / `online_duration` / `connection_count` | `voteit.messaging.Connection` |
| `login_count` | auditlog updates on `User`, by `additional_data["o"]` |
| `speaker_count` / `spoken_duration` | `voteit.speaker.Speaker` |
| `accepted_invitation_count` | `voteit.invites.MeetingInvite`, by the meeting's organisation |
| `proposal_outcomes` | `voteit.proposal.Proposal` final states |
| `content_types` | registry (see below) |

`mean_online_duration` and `mean_spoken_duration` are Django `GeneratedField`s (computed in the database).

## Background job

`jobs.py` — `populate_history_log`:

- Scheduled via `@schedule_job("0 4 * * *")` (UTC), collected when `apps.py` `ready()` imports `jobs`.
- Skips organisations that already have a log for the target date (idempotent).
- Skips "uninteresting" days — no `LogEntry` and no `Connection` activity.
- Date range filters use `mk_daterange_filter()` which produces `__gte` / `__lt` bounds on a datetime field (avoids slow `__date` lookups on unindexed columns).
- Log entries are attributed to the organisation of the object (`additional_data["o"]`, see `AuditLogMixin`), never the actor's. Actions by staff, jobs (no actor) or since deleted users still count. Entries from before that was set everywhere were backfilled by `migrations/0002`, falling back to the actor's organisation when the object was gone.
- Users can be deleted, so per-user sources lose them: connections go through `org.users` and are not counted for deleted users. Accepted, it only matters for the day before the job runs.
- `translate_action_keys()` converts auditlog integer action codes (0–3) to `create`/`update`/`delete`/`access` strings before storing in `action_types`.

## Auditlog retention: `manage.py archive_auditlog`

Not scheduled, run by hand. `--months N` (default 18) keeps N whole months plus the current one; without `--commit` it only counts. `--keep-entries` does steps 1 and 2 but not 3, and recomputes existing stats rows, so it can be rerun after fixes.
Logic lives in `archive.py` so it can be scheduled later. For each calendar month before the cutoff, oldest first:

1. **Aggregate**, while the rest of the log is still there:
   - `OrganisationPeriodStats` `month` row per org, plus the `year` row when the year is over and has none yet. Since months go oldest first, that happens on the year's first remaining month. Unique counts can't be added up from `HistoryLog`, which is why these exist. Fees are based on them.
   - `MeetingStats` per meeting with entries that month: participants (ever held `pa`), voters (actor of vote creation, plus current `Vote` rows since votes were only logged from late 2026), polls. `meeting_id` is not a FK, the row outlives the meeting. Recomputed from all remaining entries; once earlier entries of the meeting are deleted, counts only go up.
2. **Archive** to `auditlog/YYYY-MM.jsonl.gz` in `storages["auditlog_archive"]` (`AUDITLOG_ARCHIVE_ROOT`, default `var/auditlog_archive`, never under `MEDIA_ROOT`). One record per entry: id, ts, action, ct, obj, actor, o/m/ai, cid and `facts` -- the `ARCHIVED_CHANGE_KEYS` whitelist of `changes` (FK ids, roles, state, enabled, `last_login` as `true`). No `object_repr`, free text, email or IP.
3. **Delete** the exported ids, only after the file is saved. A failed run is safe to rerun: the file is overwritten and existing period rows are kept.

With `--keep-entries` a month row is always recomputed, months are deleted whole. A year row only when no earlier month of the year was deleted (archive file but no entries), see `year_complete`.

Entries from before late 2024 stored related objects by `str()` (`"Jane Doe (jane) 12"`, meeting titles) and roles in several formats. `migrations/0004` rewrote them to pk strings and sorted role code lists; values it couldn't resolve, mostly deleted users, were left as they were and archive as `null`. `parse_roles` still has to read the formats auditlog writes today.

Participants come from `MeetingRoles` log entries, where auditlog renders roles as `"{Participant (pa)}"` and only the create (or delete) entry carries the user, plus current `MeetingRoles`. `unique_online_users` comes from `Connection`, so it is only correct while those rows are kept.

`additional_data` isn't indexed, so meetings are queried in batches per month.

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

`tests/test_archive.py` — the archive command: archive contents, deletion, reruns, period and meeting stats.

`tests/test_dashboards.py` — verifies `DailyOrgVoteChart` aggregation and legend/series output.

Run with:

```bash
python manage.py test voteit.stats --keepdb --failfast
```

## Conventions

- Stats are **write-once** — never mutate `HistoryLog` or `OrganisationPeriodStats` rows after creation, except through `--keep-entries`. `MeetingStats` is the exception, see above.
- All aggregation happens in SQL (annotations, subqueries) — avoid Python-side loops over querysets.
- The stats app depends on many other apps but nothing depends on stats — keep it that way.
