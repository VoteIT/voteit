# Changelog

## v0.46 (date?)

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
