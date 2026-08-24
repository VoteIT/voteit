# Changelog

## Unreleased

Replaces the `channels-envelope` websocket library with
[chanx](https://pypi.org/project/chanx/), and upgrades pydantic from v1 to v2.
The two had to land together: envelope is pydantic v1 throughout, so it pinned
the whole codebase to v1.

### Breaking changes — frontend

- **Wire format**: `{"t": ..., "p": ..., "i": ..., "s": ...}` becomes
  `{"action": ..., "payload": ...}`. The `i` (message id) and `s` (state) fields
  are gone. Action names are otherwise unchanged apart from the next point.
- **`*.added` messages are gone.** Every one is now `*.changed`; the client
  should upsert. The 20 types that had both actions lose the `.added` one, and
  the four that only had `.added` (`er`, `vote`, `reaction`, `roles`) are
  renamed. 82 outgoing message types become 62.
  Note `reaction.changed` and `roles.changed` are *deltas*, not object upserts,
  and keep their partner actions (`reaction.deleted`, `roles.removed`) — branch
  on the action pair rather than inferring intent from the name.
- **`s.batch` and `s.batch2` are gone.** Runs of the same message now collapse
  into a generated per-type `<action>.batch`, whose payload is
  `{"items": [<the normal payload>, ...]}` — typed, and described in the schema.
  A batch may carry **one** item: live updates only collapse at
  `VOTEIT_BATCH_THRESHOLD` (3) or more, but initial state is always sent
  batched however few rows there are. Do not treat `.batch` as "several".
- **`channel.subscribed` no longer carries `app_state`.** Subscribing now
  streams: `channel.subscribed`, then the initial state as one or more of the
  new **`channel.state`** messages, then the new **`channel.state_complete`**.
- **Initial state arrives bundled and named.** A `channel.state` payload is
  `{pk, channel_type, seq, sections}`; each section is `{name, complete,
  failed, messages}`, where `name` identifies the server-side collector that
  produced it and `messages` holds ordinary outgoing messages verbatim. The
  names of every collector that will contribute are listed on
  `channel.subscribed` as `collectors`, so the client knows up front what to
  expect and, from `complete`, exactly when each part has fully arrived.
  Sections are packed to just under 1 MB per frame
  (`VOTEIT_APP_STATE_BUNDLE_BYTES`), so a meeting that used to take 50-100
  separate frames now takes one or two. A collector that fails marks its own
  section `failed` and no longer costs the client the rest of its state.
- **Component settings JSON Schema** (`/api/*-components/`) is now pydantic v2
  output: `$defs` rather than `definitions`, `anyOf` for optional fields, and
  draft 2020-12 refs.
- **AsyncAPI**: `/asyncapi/docs/` and `/asyncapi/schema/` (DEBUG only) publish
  the full message contract, and `chanx generate-client` can generate a typed
  client from it.

### Breaking changes — deployment

- **The `conn` and `ts` RQ queues are removed.** Connection tracking is now done
  inline from the consumer. Workers should run `default long`; running the old
  queue names will simply idle. Update any process manager or compose file.
- **`ASGI_APPLICATION` moves to `project.asgi.application`** (was
  `project.routing.application`).
- **New `voteit_messaging_connection` table** replaces `envelope_connection`.
  The app label is `voteit_messaging`, not `messaging`: an unrelated
  `voteit.messaging` app existed in 2021, and long-lived databases still carry
  its `messaging.0001_initial` row, which would make Django skip our initial
  migration as already applied. The migration copies existing rows;
  `envelope_connection` is deliberately left in place so this release can be
  rolled back, and will be dropped in a later one.
- The websocket now enforces `AllowedHostsOriginValidator`, which it did not
  before. Verify `ALLOWED_HOSTS` covers the SPA's origin.

### Changes

- **`channel_subscribed` is replaced by an app state collector registry.** The
  signal is gone. Each app declares `AppStateCollector` subclasses in its own
  `collectors.py` with a `name`, the `channels` they serve, an `order`, and a
  cheap `applicable()` that keeps a switched-off feature from being announced
  at all. `voteit/messaging/registry.py` holds `app_state_collectors` and
  `collectors_for()`; the names are unique project-wide because they go on the
  wire. `voteit.proposal.signals.attach_proposals` moved to
  `voteit.proposal.collectors`.
- **pydantic v2**. Messages raised by our own validators are unchanged: v2's
  `"Value error, "` prefix is stripped before the message reaches the API.
  pydantic's *built-in* messages did change, though, and there is no way around
  it — `"value is not a valid integer"` is now `"Input should be a valid
  integer, unable to parse string as an integer"`. Any client matching on error
  strings rather than field names will need updating.
  Errors from a model validator, which belong to no single field, are reported
  under `non_field_errors` (v1 used `__root__`).
- Vote serialisation is byte-for-byte identical to v1, deliberately. Serialised
  votes are used verbatim as counter keys and are hashed into
  `ballot_checksum`, so a formatting change would have split identical ballots
  across two keys for any poll open across the upgrade.
- `conlist(unique_items=True)` is replaced by an explicit validator that runs
  *after* field coercion, so duplicates differing only in case or whitespace
  are now correctly rejected on invite CSV upload — the misbehaviour noted in
  the old code.
- `Connection` gains indexes; the equivalent lookup went from a 38ms sequential
  scan to 0.1ms on a table of ~860k rows.
- **Websocket connections are visible in the admin.** `voteit.messaging` gets a
  read-only `Connection` changelist (filter by online / stale / closed and by
  organisation, sort by session duration, search by user), a live
  `.../connection/online/` page (users online, sockets per user, per-org
  breakdown, connected-for histogram, longest current sessions) and a new
  `Sockets` dashboard tab under `/admin/dashboard/` with connections-per-hour,
  session-length and close-code charts. Until now the only way to see who was
  online was the online/offline filter on the user list.
- **Stale connections are cleaned up.** `close_stale_connections` runs every 30
  minutes and stamps close code 1006 on open rows that have been silent longer
  than `VOTEIT_CONNECTION_STALE_JOB_AFTER` (1h). Nothing reaped this table
  before, so rows from crashed workers stayed "open" forever and bloated the
  partial index behind every presence query. No visible count changes — those
  rows were already outside the `online()` window — and a socket that turns out
  to be alive resets its own code on the next message. Setting
  `VOTEIT_CONNECTION_RETENTION_DAYS` (default `None`, off) additionally deletes
  long-closed rows; `voteit.stats.HistoryLog` already holds the daily
  aggregates they feed.
- First end-to-end websocket tests: previously everything was tested at the
  signal level and nothing exercised the consumer itself.
- **State machines are bound lazily.** `statemachine.mixins.MachineMixin` built
  a whole `StateChart` inside every `Model.__init__` — so once per row of every
  queryset, on the seven models that carry one. Measured at 209 µs / 30.8 kB per
  `MeetingInvite` and 946 µs / 143 kB per `Poll`, against 5.4 µs / 584 B for the
  bare model. `voteit.core.statemachines.StateMachineModelMixin` replaces it and
  builds the machine on first access to `.sm`; nothing that iterates these
  models in bulk reads it. Subscribing a moderator to `MeetingInvitesChannel` on
  a 50 000-invite meeting drops from ~7.6 s and ~1.5 GB allocated to ~0.6 s and
  ~50 MB. `.only()` / `.defer()` also become usable on these models for the
  first time: the eager machine read the deferred `state` field, turning one
  query into one per row.

### Fixes

- A websocket disconnect whose ASGI message carried no close code used to write
  the `Connection` row back as still open. It now records 1006.


## v0.47 (2026-08-17)

Continued WebSocket-to-REST migration: vote casting, bulk agenda item operations,
SFS delegation vote weights, and room text-marking are now REST endpoints instead of
incoming WebSocket messages. Dependency cleanup and a couple of small fixes round out
the release.

### Breaking changes

- **Vote casting moved to REST**: Votes are now cast via `POST /api/votes/`
  (`{"poll": 1, "vote": {...}}` or `{"poll": 1, "abstain": true}`) instead of an
  incoming WebSocket message. It's an upsert — casting again just overwrites the
  existing vote, and abstaining overwrites a previous vote (and vice versa). Returns
  `201` on first cast, `200` on update.
- **Bulk agenda item operations moved to REST**: `POST /api/agenda-items/bulk-change/`
  (state, `block_discussion`, `block_proposals`, combinable) and
  `POST /api/agenda-items/bulk-delete/` (blocked while the meeting is ongoing) replace
  the equivalent WebSocket messages.
- **SFS delegation vote weights moved to REST**: `POST /api/sfs-delegation-voters/{pk}/set/`
- **Room text-marking moved to REST**: `POST /api/rooms/{pk}/mark-text/` relays a text
  selection to `RoomChannel` subscribers.

### Changes

- **New votes schedules jobs**: Rather than sending one message per vote to all
  subscribers, new votes schedules exactly one job unless it already exists.
  This removes one of the major bottlenecks with voting throughput.
- **`python-graph-core` and `setuptools` dependencies dropped**: Both were legacy
  leftovers from `python3-vote-core`, unrelated to VoteIT itself.
- **Poll vote validation generalised**: The "does this vote reference real proposals"
  check used by Dutt, Schulze and Scottish STV is now a shared
  `PollMethod.unmatched_proposal_pks()` helper.
- **Tests use a dedicated Redis db**: `make test`, `make test-deps` and `make coverage`
  now point `REDIS_CACHE_LOCATION` at db `9` instead of sharing the dev cache's db.

### Fixes

- **`/invites/bulk-revoke/` contained a bug that caused server error.

## v0.46 (2026-06-18)

The headline change is a full replacement of `django-fsm` with `python-statemachine` across all
workflow-driven models. The new state machines are more explicit, testable, and expose a uniform
REST interface. Several smaller improvements and fixes accompany the refactoring.

### Breaking changes

- **`django-fsm` removed**: All state-machine logic now lives in `python-statemachine` (`StateChart`
  subclasses). Models no longer carry FSM field helpers — state is stored in the existing
  `state` field but driven by `instance.sm`. Any code that called FSM transition methods
  directly must be updated to use `instance.sm.<event>()`.
- **Component state replaced with `enabled` bool**: `MeetingComponent` and `OrganisationComponent`
  no longer use a workflow for on/off state.

### New features

- **Unified statemachine REST endpoint**: `GET /api/state-machines/` returns all
  state machines (state, available events, metadata).
- **Event endpoint returns available transitions**: The `POST /{id}/event/` endpoint now includes
  the current state and the list of currently allowed events in its response.
- **Admin action for statemachine transitions**: Admins can now trigger state-machine events
  directly from the Django admin change list.
- **Member dialects moved into core repo**: The `sfs`, `skk`, and `skr` voting-behaviour plugins
  (previously in the separate `member_dialects` sub-package) are now part of `voteit/app/` and
  no longer require a separate install. The `member_dialects` dependency has been dropped.

### Changes

- **Poll execution restructured**: Several poll transitions (collect → calculate → finish) are
  now automatic, reducing the need for explicit moderator actions. Ballot finalisation
  (checksum, weight application, ER-cleanup) is a dedicated method on the model.
- **Polls require ongoing meeting and agenda item**: A poll can no longer be started if the
  meeting or agenda item is not in an ongoing state.
- **Group deletion allowed**: Meeting groups can now be deleted through the rest interface. Bulk operation requires upcoming meeting.
- **Token API: cap at 5 active keys per meeting**: Creating a sixth active API key for a meeting
  is now blocked.

### Fixes

- **Switch user authentication backend fixed**: The wrong authentication backend was selected, causing
  users to never be authenticated. Only applied to the switch user operation.
- **Proposals editable when agenda item is closed** (#378): Proposal editing was
  blocked when the parent agenda item was closed; this is now allowed.
- **Empty electoral register not created when disabled**: An empty ER record was created even
  when the ER policy was disabled; the guard now prevents this.
- **Preview cooldown removed**: The preview transition had an unintended cooldown.

## v0.45 (2026-06-03)

Continued REST migration, invite improvements, security hardening,
and project housekeeping (AGPL licence, README, CONTRIBUTING).

### New features

- **Invite file upload endpoint**: Invites can now be imported via a file upload REST endpoint.
  Blank lines are allowed (useful when pasting from Excel). Includes a session lock to prevent
  concurrent imports, and improved importer structure with stricter validation.
- **Invite and annotations combined**: Instead of separate actions, invites can be created and/or annotated
  via the same REST action.
- **Meeting clone endpoint**: New REST endpoint for cloning meeting data.

### Changes

- **Proposals no longer locked for vote after poll**: All proposals that aren't approved or denied are now published again.
- **Meeting groups — bulk REST endpoints**: `bulk_create` and `bulk_delete` for meeting groups
  are now REST endpoints rather than WebSocket messages. `bulk_delete` is restricted to upcoming meetings.
- **Management command aligned with REST**: The invite management command now mirrors the REST
  interface behaviour.
- **Speaker lists**: Starting a new speaker while another is speaking was blocked before. Now the old speaker is simply stopped.

### Security

- **XML anchor attack prevention**: Blocked anchor entities in XML/HTML input to prevent
  billion-laughs-style attacks.
- **Extra sanitisation layer in schemas**: An additional strip pass is applied in schemas to avoid
  depending solely on downstream sanitisers.
- **Rich-text field enforcement**: Fields that accept HTML are now `RichTextField` so that HTML
  cleaning fires correctly. (The Django models `clean` methods never fire in DRF views.)
- **Unsigned file upload size limit**: Unsigned file uploads are permitted but at a reduced
  maximum size. (Related to imports)

### Project

- **AGPL licence**: The project is now licensed under AGPL. Licence files added.
- **README and CONTRIBUTING docs**: New top-level documentation for contributors.
- **GitHub PR template** and **security policy** added.
- **ruff in pre-commit**: `ruff` is now run as a pre-commit hook.

## v0.44 (2026-05-25)

Focused on optional meeting token-based API-access and moving messages that don't need to be websocket operations
to regular rest interfaces in preparation of refactoring to ChanX.

### New features

- **Token API**: New `voteit.token_api` app for programmatic access to meeting resources.
API keys are scoped to a single meeting and carry per-resource permission scopes
(`resource.action` or `resource.*`). Keys are issued via the admin or a moderator-only
REST endpoint, expire after 120 days, and can be revoked.
Includes views for invites and meeting info, rate limiting, and full auditlog attribution.
See `voteit/token_api/README.md`. #374

### Changes

- **`Role` now subclasses `str`**: `Role` objects serialize directly as JSON, compare equal to plain strings, and hash the same way.
- **Internal API changes**: The following resources use REST instead of messages, in preparations for websocket refactoring:
  - **Role**: Meetings, speaker systems, and organisations now expose `available`, `add_roles`, and `remove_roles` REST actions, replacing the previous WebSocket message-based role assignment.
  - **Reactions**: Reactions can now be set, removed, and listed via `POST/DELETE /api/reactions/`.
  - **Active users**: `ActiveUserViewSet` with list, retrieve, and purge actions.
  - **Electoral register creation**: `trigger_create` and `manual_create`.
  - **Agenda `last_read`**: The `update_last_read` action.
  - **Speaker system**: New `SpeakerSystemRolesViewSet`.

## v0.43 (2026-05-18)

### New features

- **User image upload**: Users can now upload a profile image. A `purge_user_images` management command is available to clean up orphaned image files.
- **User merger (admin)**: Admin interface for merging duplicate user accounts, transferring roles, votes, proposals, and other relations to the surviving account.
- **User deactivation job**: Background job to automatically deactivate user accounts that have not been used.
- **Online view in organisation admin**: Optional per-organisation view showing currently connected users, implemented as a separate admin page to avoid costly connection queries in the main list.

### Changes

- **Voter weight refactored**: Voter weight is now stored as `voter_data` on the poll model (via data migration), replacing the separate `VoterWeight` model. Fixes #327.
- **`last_modified_by` removed**: The unused field has been dropped from `AgendaItem`, `DiscussionPost`, `Poll`, `Proposal`, `TextDocument`, and `Organisation`. Auditlog covers this information.
- **Proposal optimisations**: Faster queryset handling with `select_subclasses`; fixes a bug where subclasses were not selected in certain views.
- **Agenda speedups**: Reduced query count on agenda item endpoints.
- **`get_object` caching**: Permission-checking views now cache `get_object()` to avoid redundant fetches per request.
- **Social auth cleared on user deactivation**: Deactivating a user now removes associated social auth entries.
- **Dialect install/uninstall endpoints**: REST endpoints for installing and removing meeting dialects.
- **Bugfix — dialect uninstall no longer clears group memberships**: Uninstalling a dialect that had roles was incorrectly removing group memberships. Fixes #369.
- **python-vote-core updated**: Upgraded to avoid deprecated dependencies. Fixes #339.
