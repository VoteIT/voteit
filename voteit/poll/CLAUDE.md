# voteit/poll

The poll app handles the full lifecycle of a vote: creation, configuration, voter eligibility, casting votes, tallying, and publishing results. It is the most complex app in VoteIT.

## Core Models

**Poll** — the primary model. Belongs to an `AgendaItem` (and transitively a `Meeting`). Key fields:
- `method_name`: selects the voting algorithm from the `poll_methods` registry
- `settings_data` / result via `settings` property: Pydantic model specific to the poll method
- `ballot_data` + `ballot_checksum`: SHA-512–protected vote tally written on close; cleared when entering `failed` to allow retry, then immutable once in `finished`/`withheld`
- `electoral_register`: snapshot of eligible voters taken at poll open
- `proposals` (M2M): the proposals being voted on; locked into VOTING state while poll is ongoing
- `withheld_result`: when True the result is finished but hidden from participants

**ElectoralRegister (ER)** — immutable snapshot of eligible voters and weights (`voter_data` dict of `{user_pk: weight}`). `voter_data` is write-protected after creation; use `set_voters_from_dict()` to populate before saving.

**Vote** — one vote per (user, poll). `vote_data` is a string; converted to/from the method's Pydantic vote model via `vote` property. Votes are upserted (update-or-create), never deleted via API. Abstentions set `abstain=True` and clear `vote_data`.

**VoteTransfer** — delegates voting rights from `source` to `target` within a meeting. Unique on source per meeting. Deleted automatically when either user leaves the meeting.

## State Machine

`PollStateMachine` in `statemachines.py`. Events are sent via `poll.sm.send(event_name, ...)` or `POST /polls/{id}/event/` (`StateMachineMixin`). Key guarded events:
- `make_upcoming` / `make_ongoing`: validates settings (Pydantic), ER policy, method `start_check()`, and if manual ER is required
- `close`: `on_close` sets the timestamp, cleans up any votes no longer in the ER, then calls `calculate_result()`. Exceptions from `calculate_result` are caught and logged (not re-raised) so the `ongoing → closed` transition is never rolled back.
- Auto-transitions from `closed` (evaluated immediately, in order):
  - `→ withheld` / `→ finished`: when ER is populated, valid votes exist, and result was computed successfully
  - `→ no_result`: when there are no valid non-abstain votes, or the ER is empty/missing
  - `→ failed`: catch-all when ER and votes exist but `result_data` is still `None` (calculation error). Moderator can retry by calling `close` again once the underlying issue is fixed.
- `withheld → finished` (`publish_result` event): publishes results and sets proposals

## Registries (Pluggable Components)

Three registries in `registries.py`, each a typed dict used as a decorator:

```python
@poll_methods
class MyMethod(PollMethod): ...

@er_policy
class MyPolicy(ElectoralRegisterPolicy): ...

@vote_transfer_policies
class MyPolicy(VoteTransferPolicy): ...
```

### PollMethod ABC (`abcs.py`)

Required interface:
- `name`: registry key
- `vote_schema` / `result_schema`: Pydantic models
- `vote_to_str(data)` / `vote_to_obj(text)`: string ↔ Pydantic round-trip
- `calculate_result(counter)`: receives `Counter({vote_data_str: weight})`, returns `result_schema` instance
- `start_check()`: raise `PollStartError` if poll can't start (e.g. wrong proposal count)
- Optional: `settings_schema`, `validate_vote(msg)`, `historic = True`

Available methods in `app/polls/`: `simple`, `majority`, `combined_simple`, `ranked`, `irv`, `schulze`, `scottish_stv`, `dutt`.

### ElectoralRegisterPolicy ABC

Key attributes:
- `allow_manual` / `require_manual`: moderator ER creation controls
- `allow_trigger`: moderator can trigger ER creation on demand
- `allow_poll_er_change`: ER can be updated on ongoing polls
- `handles_vote_weight`, `handles_active_check`, `handles_delegate_to`: capability flags

Key methods:
- `get_voters(**kwargs)` → `{user_pk: weight}`: computes eligible voters
- `apply(poll, target_state)`: called on poll state transitions; attaches/updates ER
- `create_er(force=False)`: creates and attaches ER to meeting; decorated with `@ensure_atomic`

Available policies in `app/er_policies/`: `auto_always`, `auto_before_poll`, `manual_trigger`, `manual`, `presence_check`, and group-voting variants.

## Vote Counting Flow

1. `finalize_vote_data()` on Poll:
   - Iterates all `Vote` objects, applies ER weight per user
   - Builds `Counter({vote_data_str: weight})`
   - Serializes to JSON → SHA-512 → stores in `ballot_data` / `ballot_checksum`
2. Poll method's `calculate_result(counter)` → result Pydantic object
3. `set_proposals_from_result()` transitions linked proposals (approved/denied/no_result)

Abstentions are tallied separately and never enter the counter.

## REST API

ViewSets registered in `rest_api/views.py` (all under `/api/`):

| ViewSet | Basename | Notable actions |
|---------|----------|-----------------|
| `PollViewSet` | `poll` | CRUD + state transitions via `StateMachineMixin` (`POST /polls/{id}/event/`) |
| `ElectoralRegisterViewSet` | `electoral-registers` | read-only + `trigger-create` + `manual-create` |
| `VoteTransferViewSet` | `vote-transfer` | CRUD + `reassign` action |
| `ElectoralRegisterPoliciesViewSet` | `electoral-register-policies` | list only (metadata) |
| `ExportERViewSet` | `export-electoral-register` | `csv` and `json` actions |

Vote creation/update is handled via WebSocket messages (`messages.py`), not a REST endpoint.

## WebSocket / Channels

Handlers in `signals.py` (subscribed to `channels-envelope` events):

- **On subscription**: push current poll state, votes, ER, vote transfers to the joining user
- **On poll change**: broadcast `PollAdded`/`PollChanged`/`PollDeleted` to appropriate channels
- **On vote cast**: send `PollStatus` (aggregate counts) to meeting channel; send `GenericVoteResponse` to the voter's user channel

Message types are Pydantic models in `messages.py`. `AddVote` (abstract) is the base for vote messages; subclass it to add a new vote type.

## Permissions

Defined in `rules.py` using the `rules` library. Key predicates:

- `poll.add` / `poll.change_state`: requires `ROLE_MODERATOR`
- `vote.add`: poll must be `ongoing` and user must be in the electoral register
- `vt.add` (vote transfer): requires `ROLE_POTENTIAL_VOTER` or moderator, meeting must be upcoming/ongoing, and vote transfers must be enabled on the meeting

## Proposal Side Effects

Poll transitions automatically change proposal states:
- `upcoming` / `ongoing`: proposals → `VOTING` (locked)
- `canceled` / `unpublish`: proposals → `PUBLISHED`
- `finished`: proposals → `APPROVED` or `DENIED` per result; proposals with no result → `PUBLISHED`

Never change proposal states manually when a poll is involved.

## Testing

Run poll tests:
```bash
python manage.py test voteit.poll --keepdb --failfast
```

Tests are under `tests/` (models, rules, signals, messages, auditlog) and `rest_api/tests/` (views, serializers) and `app/polls/tests/` and `app/er_policies/tests/` (one file per method/policy).

`testing.py` exports `UnrestrictedVoteTransferPolicy` and `UnrestrictedVoteTransferER` for use in other apps' tests that need a poll without transfer restrictions.

## Key Invariants

- `ballot_data` and `ballot_checksum` are immutable once the poll reaches `finished` or `withheld`. In `failed` state they are cleared by `on_enter_failed` so retrying via `close` can re-run `finalize_vote_data()`.
- `ElectoralRegister.voter_data` is write-protected after creation.
- One vote per (user, poll) — enforced by DB unique constraint; use `update_or_create`.
- A poll with only abstentions → `no_result`, not `finished`.
- Proposal locking/unlocking is a side effect of poll transitions — do not do it separately.
