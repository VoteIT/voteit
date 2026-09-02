# Reviewing `chanx-pydantic2`

Replaces `channels-envelope` with [chanx](https://pypi.org/project/chanx/) and
upgrades pydantic v1 → v2. **18 commits, 194 files, +4287/−2375.**

The two changes had to land together: envelope is pydantic v1 throughout
(`parse_raw`, `.dict()`, `@validator`), so it pinned the whole codebase to v1
and the swap could not be staged.

> **Companion branch**: `src/voteit_org` is a separate git repo and has its own
> `chanx-pydantic2` branch with one commit. `make test-deps` fails without it.
> Merge them together.

## State

| | |
|---|---|
| `make test` | 2046 passed (2016 on main) |
| `make test-deps` | 6 passed |
| `manage.py check` | no issues |
| `makemigrations --check` | no changes |
| `ruff check voteit/ src/` | clean |

---

## Suggested review order

The commits are meant to be read in order; each is self-contained and the
message explains *why*, not just what.

| # | Commit | What to look for |
|---|---|---|
| 1 | `b1f713c` delete dead websocket code | Confirm nothing you rely on is being deleted |
| 2 | `d7fa965` pydantic v2 prep (dual-compatible) | **Semantics-preserving under v1** — the field-shape snapshot proved it |
| 3–4 | `a786f75`, `8768614` Connection model + readers | The DB change; see "app label" below |
| 5 | `ca097a5` **dependency flip** | Tree is red from here until 13 |
| 6–8 | `3369d13`, `c7732d1`, `87c07c0` the new layer | The design: batching, subscribe, message conversion |
| 9 | `1517645` finish pydantic v2 | **Highest-risk commit** — read the message in full |
| 10–15 | test port + `7fd7454` | `7fd7454` is a real bug fix, not a test fix |
| 16 | `4f974d1` end-to-end consumer tests | The only tests that exercise the consumer |
| 17 | `ed110de` docs | Contract for the SPA team |

Start with `voteit/messaging/CLAUDE.md` for the architecture, then
`voteit/messaging/utils.py` (everything funnels through `_send_now`).

---

## Highest-risk items

Ordered by what would hurt most if wrong.

### 1. Vote serialisation — would have corrupted live ballots
`Poll.finalize_vote_data` uses the serialised vote string **verbatim as a
Counter key** and hashes it into `ballot_checksum`. pydantic v2's
`model_dump_json()` emits compact separators where v1 used `", "` / `": "`, and
every ballot in the production database is the v1 form. A poll open across the
deploy would have split identical votes across two counter keys and changed its
checksum.

`PollMethod.vote_json` (`voteit/poll/abcs.py`) reproduces v1's bytes exactly.
Verified by round-tripping real `combined_simple` and `majority` rows pulled
from the dev database — `model_dump_json()` differed on *every* one.

Only `majority`, `combined_simple` and `historic` were affected; `dutt`,
`schulze` and `scottish_stv` build their strings with `json.dumps` by hand.

**Worth checking**: is there any other place a pydantic-serialised string is
compared, hashed or used as a key?

### 2. App-label collision — would have broken every existing deployment
`voteit.messaging` already existed as an app in 2021 (`9f9b455`, removed in
`4275017`). Long-lived databases still carry its `messaging.0001_initial`
record and a stale `messaging_connection` table with a different schema, so
with the default label Django considers our initial migration already applied,
skips it, and `0002` then fails on the missing column.

Fixed with an explicit `label = "voteit_messaging"` → table
`voteit_messaging_connection`.

**Worth checking**: other orphaned app labels in production `django_migrations`
(`bug_reports`, `authtoken`, `social_auth`, `default` are all present in dev and
no longer installed). None collide today, but the same trap exists for any
future app.

### 3. Swapped batch message classes — caught, but the class of bug is the point
The script that converted envelope's manual `Batch` accumulation into
`AppState.add_batch` paired each block with its message class by AST-walk order,
which is breadth-first and not source order. In `poll/signals.py` that swapped
two blocks: vote transfers were being announced as `poll.changed` and the
moderators' poll list as `vote_transfer.changed`.

Fixed in `7fd7454`; every `add_batch` call was then audited against the
serializer feeding it, and poll was the only file affected.

**Worth checking**: this is exactly the kind of error that survives a green test
suite. Spot-check a few `add_batch` calls yourself against their serializer.

### 4. Two pydantic v2 ordering traps
- **`mode="before"` validators run in reverse declaration order** where v1 ran
  `pre=True` in declaration order. Broke `AgendaItemData.proposals`, where a
  manager-resolving validator has to run before the type-selecting one. Merged
  into a single validator. A scan confirmed this was the only field with more
  than one before-validator.
- **`always=True` validators silently stop raising.** v2 field validators never
  run when a field falls back to its default. `room/messages.py` had two, with
  doctests that depend on exactly that behaviour. Converted to one
  `model_validator(mode="after")`. `meeting/schemas.py:93` and
  `export_import/schemas.py:303` had the same flag and were reviewed
  individually — `check_settings` uses `model_fields_set` to preserve "only run
  when supplied".

### 5. User-facing error messages
pydantic v2 prefixes every validator `ValueError` with `"Value error, "` and
reports them all as type `value_error` (the v1 dotted
`value_error.datacolvalidation` form is gone).

- The prefix is stripped in `pydantic_to_drf_validation_error`, so messages our
  own validators raise are unchanged. pydantic's built-in messages *did* change
  (`"value is not a valid integer"` → `"Input should be a valid integer, unable
  to parse string as an integer"`); nothing can be done about that.
- A model validator's error has an empty `loc` in v2 where v1 used
  `("__root__",)`. It is now reported under `non_field_errors`; the first cut
  dropped it, answering an invalid request with a bare `400 {}`.
- The invites CSV-upload branches now `isinstance`-check the original exception
  out of `ctx`, which is sturdier than string matching. `voteit.invites` is
  fully green, including the "duplicate rows" message test.

**Worth checking**: any frontend that matches on error *strings* rather than
field names.

### 6. Indexes added beyond the agreed model spec
The `Connection` model is exactly as specified, but I added migration `0003`
with three indexes. Rationale: the envelope model got a `user_id` index for free
from its `unique_together`, these are hot admin/stats queries, and the table is
never reaped. On a 863k-row copy of the dev database the "currently online"
lookup went from a **38.5 ms parallel sequential scan to 0.125 ms**.

**This is the most likely thing you'll want to reverse** — drop `0003` if you
disagree.

---

## Judgement calls you may want to revisit

| Decision | Where | Why, and the alternative |
|---|---|---|
| `ContextChannel` kept rather than dissolved into per-domain handlers | `voteit/messaging/channels.py` | 7 domain channels + 2 built-ins share one shape; dissolving would mean 9 handlers and 27 message classes, and `channel.recheck` becomes a 9-way dispatch. Votera dissolved it because it has only two, with different shapes. |
| Batch threshold stays at 3 | `VOTEIT_BATCH_THRESHOLD` | At 2 the wrapper costs more than it saves; moving it changes the wire shape at the boundary the frontend implements against. |
| Group fan-out uses chanx's *unvalidated* passthrough | `_send_now`, `VOTEIT_WS_FAST_FANOUT` (default `True`) | The typed path re-validates per recipient — ~3× CPU in a 500-participant meeting, for messages already type-safe at the publisher. Set the flag to `False` for chanx's own path; the wire frame is identical either way. |
| Connection writes inline, `conn`/`ts` queues dropped | `ConnectionMixin` | Without an FK or unique constraint these are a bare INSERT and a bare UPDATE. Removes 2 queues, 2 redis DBs, 2 compose services. |
| `AllowedHostsOriginValidator` added | `project/asgi.py` | The socket was **not** origin-checked before. Correct, but new — verify `ALLOWED_HOSTS` covers the SPA origin before deploying. |
| Datetimes normalised for `extra="allow"` payloads | `voteit/messaging/base.py` | v2 serialises *extra* datetimes as UTC-with-`Z` where v1 produced local isoformat. Publishers passing `.values()` output (proposal, notes) would have silently changed format. |

---

## Frontend contract changes

Everything the SPA team needs is in the CHANGELOG entry. In short:

1. `{"t","p","i","s"}` → `{"action","payload"}`. `i` and `s` are gone.
2. **No `*.added` action survives** — upsert on `*.changed`. 82 types → 62.
   ⚠️ `reaction.changed` and `roles.changed` are *deltas*, not object upserts,
   and keep their partner actions (`reaction.deleted`, `roles.removed`). Branch
   on the action pair, not the name.
3. `s.batch` / `s.batch2` → per-type `<action>.batch` with
   `payload: {items: [...]}`.
4. `channel.subscribed` no longer carries `app_state`. Subscribe now streams:
   `channel.subscribed` → state messages → **`channel.state_complete`** (new).
5. Component settings JSON Schema is draft 2020-12 (`$defs`, `anyOf`).

`/asyncapi/docs/` (DEBUG) renders the whole contract and
`chanx generate-client` can generate a typed client from it.

---

## Deployment checklist

1. `ASGI_APPLICATION` is now `project.asgi.application`.
2. Workers must run **`default long`**. The `conn` and `ts` queues no longer
   exist; a worker started on them will simply idle.
   *(Two rqworkers on this machine are still running the old queue list.)*
3. `migrate` **after** deploying the code. `0002` reads `envelope_connection`
   via raw SQL guarded by an `information_schema` check, so it is a no-op on
   fresh installs and never imports the envelope app.
4. `envelope_connection` is deliberately **left in place** so this release can
   be rolled back. Dropping it is a follow-up.
5. Verify `ALLOWED_HOSTS` covers the SPA origin (see origin validator above).

---

## Deliberately not done

- **`envelope_connection` is not dropped.** Follow-up release, to keep rollback
  possible.
- **`voteit/presence/`** is documented as dead but still referenced by
  `poll/app/er_policies/presence_check.py`. Left alone.
- **`src/member_dialects/`** is a stale directory — nothing references it in
  `pyproject.toml`, `uv.lock`, `Makefile`, settings or `project/`. Deleting it
  is a separate tidy-up.
- **`ExportMeetingMeta.created: datetime = now()`** evaluates its default at
  import time, so it is frozen at process start rather than per instance. A
  pre-existing bug, found while building the shape-diff harness; `default_factory`
  would fix it. Left alone as out of scope.

---

## Where the tests are weak

Be sceptical here — this is where I'd focus review effort.

- **The admin views and dashboards have no test coverage at all**
  (`core/admin.py::OnlineFilter`, `organisation/admin.py::online_view`,
  `stats/dashboards.py`). The rewritten `Connection` queries were verified by
  running each one against the dev database by hand, not by tests.
- **`stats/jobs.py`** has the hardest rewrite in the branch — four `OuterRef`
  subqueries that went through the removed FK. Covered by tests, but worth
  reading closely. The plan's suggested check: run `populate_history_log` for
  yesterday against a production copy and compare `connection_count`,
  `online_duration` and `user_online_count` to the pre-migration values.
- **The end-to-end consumer tests use `InMemoryChannelLayer` and fakeredis**, so
  they do not exercise redis pub/sub or cross-process fan-out.
- **No load test has been run.** `locust/locustfile.py` is updated to the new
  protocol but has not been run against staging. That is the only way to
  confirm `VOTEIT_WS_FAST_FANOUT` and the chanx startup schema-generation cost
  (124 message types) are acceptable.
- **27 `channel_subscribed` receivers and 72 `sync_publish` call sites** were
  converted largely mechanically. The suite covers them, but the swapped-class
  bug above shows mechanical conversion can produce plausible-but-wrong results
  that still pass.

---

## Verifying locally

```bash
uv sync
make test          # 2046 expected
make test-deps     # needs the voteit_org branch checked out
ruff check voteit/ src/
python manage.py check
python manage.py makemigrations --check --dry-run
```

Structural invariants:

```bash
# 62 base + 62 batch actions, all reachable, no *.added
python manage.py shell -c "
from voteit.messaging.consumer import VoteitConsumer
from voteit.messaging.registry import _outgoing
actions = sorted(_outgoing)
base = [a for a in actions if not a.endswith('.batch')]
print(f'{len(base)} base + {len(actions)-len(base)} batch')
assert not set(actions) - set(VoteitConsumer._EVENT_HANDLER_INFO_MAP)
assert not [a for a in base if a.endswith('.added')]
print('incoming:', sorted(VoteitConsumer._MESSAGE_HANDLER_INFO_MAP))"
```

Manual smoke, in this order — the batch check is the one that matters most:

1. `/asyncapi/docs/` — all types render, no `*.added`.
2. `wscat`: connect → `s.versions`; `s.ping` → `s.pong`; subscribe to
   `participants` → `channel.subscribed`, state messages, `channel.state_complete`
   — one stream carrying what used to need a second `meeting` subscribe too
   (`meeting.roles`, `room.rooms`, `speaker.systems`, `poll.own_votes` …).
3. Subscribe to `moderators` as a non-participant → `channel.subscribe_error`
   and nothing else. Subscribe to `meeting` at all → `channel.subscribe_error`,
   `"Unknown channel type"`.
3b. Edit a room with a participant tab and a moderator tab open → **both** get
   `room.changed` exactly once.
4. **Add 5 proposals in one request → the other tab gets ONE
   `proposal.changed.batch` with 5 items. Add 2 → two individual messages.**
5. Remove a moderator role via REST → `channel.left`.
6. On a production copy: `SELECT count(*)` on `envelope_connection` vs
   `voteit_messaging_connection` must match after `migrate`.
7. On a production copy: `vote_to_obj(vote.data)` over every vote in a finished
   `majority` and `combined_simple` poll — zero exceptions, results match.
