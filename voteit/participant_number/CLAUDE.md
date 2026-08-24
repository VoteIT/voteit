# voteit.participant_number

This feature is no longer supported but is here for historic reasons.

Assigns short numeric aliases to meeting participants. The primary use case is in-person plenary sessions with poor internet where participants hold up numbered signs; a moderator types the number to queue them rather than searching by username. Numbers are scoped to a meeting via `PNSystem`, so the same user can hold different numbers in different meetings.

## Models

**`PNSystem`** — a one-to-one container attached to a meeting (`meeting.pn_system`). Extends `MeetingContext`. A meeting has no participant number functionality until a `PNSystem` is created for it. The `meeting` field is nullable so that the system record can exist transiently without a meeting, but in practice it is always created together with a meeting reference.

Key method: `get_user(pn: int, default=None)` — looks up the user assigned to a given number; returns `default` if none found.

**`ParticipantNumber`** — the actual assignment: one user gets one number within a `PNSystem`. Key fields:

- `number` (`PositiveSmallIntegerField`, blank) — auto-assigned on save if not provided: finds the highest existing number and increments by 1, starting from 1. Can be set explicitly (e.g. on import).
- `user` — FK to the auth user, `on_delete=RESTRICT` (cannot delete a user while they have a PN).
- `pns` — FK to `PNSystem` with `related_name="numbers"`.
- `created` — auto-set timestamp, not editable.

Uniqueness constraints: one number per `PNSystem`, and one user per `PNSystem`. Both are enforced as database-level `UniqueConstraint`s.

## Permissions

There is no `rules.py` in this app. Permission checks delegate to the related meeting — if you can manage the meeting, you can manage its participant numbers. This is an explicit design choice documented in `PNSystem`'s docstring.

## WebSocket messages (`messages.py`)

All messages are outgoing-only, published via `broadcast_meeting`.

- **`pn.changed`** (`PNChanged`) — a number was assigned or updated; payload: `{meeting, number, user, pk}`. There is no `.added`; the client upserts on `pk`.
- **`pn.changed`** (`PNChanged`) — an existing assignment was updated; same payload.
- **`pn.deleted`** (`PNDeleted`) — an assignment was removed; payload: `{pk}` only (inherits from `BaseObjectDeleted`).

## Signals (`signals.py`)

- `participant_number.numbers` collector on `ParticipantsChannel` + `ModeratorsChannel` — all current participant numbers as one `pn.changed.batch`. `applicable()` returns False when the meeting has no `PNSystem`.
- `post_save` on `ParticipantNumber` — publishes `PNChanged` on both creation and update via `broadcast_meeting`. Skips if `pns.meeting` is `None`. Uses `@disable_on_raw_save` to avoid firing during data loads.
- `pre_delete` on `ParticipantNumber` — publishes `PNDeleted` synchronously before the row is removed.

## Management command

`import_pns` — bulk-loads participant numbers from STDIN for a given meeting.

```bash
python manage.py import_pns -m <meeting_pk> [--clear]
```

Input format: one row per line, `<number> <email>`. Only users already in the meeting's participant list are matched (by email). The `--clear` flag deletes all existing numbers before importing. The command validates for duplicate numbers and duplicate emails in the input before writing, and wraps the whole import in a transaction.

## Notable patterns

- **Auto-increment on save**: `ParticipantNumber.save()` implements its own sequential numbering when `number` is `None`. It queries for the current max and adds 1. This is not atomic — concurrent creates under high load could theoretically collide, but the DB constraint will catch it.
- **No PNSystem, no feature**: Nothing in the codebase creates a `PNSystem` automatically. It must be created explicitly (via admin or the import command). There is no component gate or feature flag.
- **Deletion protection on users**: `on_delete=RESTRICT` on `ParticipantNumber.user` means you cannot delete a user who has participant numbers. The meeting-scoped container (`PNSystem`) cascades on meeting deletion.
- **`PNSystem.meeting` is nullable** in the database, but there is no documented use case for a detached system. The initial migration shows it was nullable from the start, likely to allow creating the record before associating it.

## Tests

```bash
python manage.py test voteit.participant_number --keepdb --failfast
```

- `tests/test_models.py` — `get_user` lookup and both uniqueness constraints.
- `tests/test_signals.py` — app state population on channel subscribe; `PNChanged`, `PNDeleted` WebSocket messages; auto-increment numbering verified via signal test.
- `tests/test_docs.py` — runs any doctests found in the package.
