# Changelog

## v0.44

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

## v0.43

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
