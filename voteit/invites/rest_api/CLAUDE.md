# voteit/invites/rest_api

REST API layer for the invites package. Three distinct audiences, each with its own ViewSet and auth mechanism.

## ViewSets

### `MeetingInviteViewSet` (`/api/meeting-invites/`)
Moderator-facing. Requires meeting moderator role. Registered via `@router.register`. Uses `StateMachineMixin` (replaces the old `TransitionsMixin`).

- `POST /` — create/update invites from JSON. Supports annotations in the same request (see below).
- `POST /import/` — create/update invites from an uploaded file (XLSX, ODS, CSV, TSV).
- `GET /{pk}/` — retrieve annotation data for a single invite (not a standard list).
- `DELETE /{pk}/` — delete an invite.
- `POST /bulk-delete/` — delete multiple invites by PK list (validates all belong to same meeting).
- `POST /bulk-revoke/` — transition multiple invites to `revoked`.
- `POST /clear-annotations/` — remove all clearable annotations from a list of invite PKs.
- `POST /{pk}/event/` — send a state machine event (currently only `revoke`). Request: `{"event": "revoke"}`. Response 200: `{"state": "revoked"}`.
- `GET /state-machine/` — returns state machine definition (states, events) for the frontend.

Queryset is scoped to meetings where the requesting user is a moderator, and excludes archived meeting states. Uses `ForceMeetingWithRoleFilter` — requests without a `meeting` query param return no results.

### `MatchInvitesViewSet` (`/api/match-invites/`)
Service endpoint for the external ID-proxy login system. Auth: `HasIDProxyAPIKey` (API key via `HTTP_API_KEY` header, setting `ID_PROXY_API_KEY`).

- `POST /query/` — find open invites matching identity data (scope+data pairs).
- `POST /{pk}/reject/` — reject a specific invite. Queryset enforces the identity match, so 404 if identity doesn't match the invite.

Input serializer: `InviteQuerySerializer` — accepts a list of `{scope, data, validated}` objects. `scope` maps to adapter names (e.g. `email`, `swedish_ssn`).

### `HandleMatchedInvitesViewSet` (`/api/handle-matched-invites/`)
For authenticated local users accepting/rejecting their own invites. Auth: `IsAuthenticated`.

- `GET /` — list open invites matching the user's identity data from their ID-proxy `UserSocialAuth`.
- `POST /{pk}/accept/` — accept; grants roles and applies group annotations.
- `POST /{pk}/reject/` — reject.

Queryset uses `get_idproxy_user_data(user)` to extract identity data and scopes results to `user.organisation`.

### `InviteDataTypesViewSet` (`/api/invite-data-types/`)
Lists registered adapter types. Filtered by the org's provider scope (defaults to `["email"]` if no provider). Returns `InviteDataTypesSchema` dicts.

## JSON create endpoint (`POST /api/meeting-invites/`)

Input:
```json
{
  "meeting": 1,
  "roles": ["pa"],
  "data": [
    {"email": "alice@example.com", "group": "committee", "grouprole": "chair"},
    {"email": "bob@example.com", "group": "committee"}
  ],
  "dryrun": false
}
```

Each item in `data` is a flat dict. The registry distinguishes identity fields (e.g. `email`, `swedish_ssn`) from annotation fields (e.g. `group`, `grouprole`). At least one identity field is required per item. Annotation fields are optional and per-item.

Response:
```json
{
  "invites": {"added": 2, "changed": 0, "existed": 0},
  "annotations": [{"name": "group", "added": 2, "changed": 0, "existed": 0}],
  "dryrun": false
}
```

Validation pipeline (`InviteCreateSerializer`):
1. Each identity key normalised via adapter schema; each annotation key accepted as a string.
2. `reg.check_column_req` — cross-column constraints (e.g. `grouprole` requires `group`).
3. `reg.preflight` — normalises annotation values in-place (strip, lowercase).
4. `reg.check_intersections` — identity-only conflict check.
5. `reg.run_validators` — DB-level checks (e.g. group IDs must exist in the meeting).
6. `_raise_if_moderator_lockout` — prevents downgrading existing moderators.

Column ordering for the registry is computed by `_items_to_columns`: user-data keys sorted alphabetically, then annotation keys in registry registration order (ensuring `group` always precedes `grouprole`).

## File import endpoint (`POST /api/meeting-invites/import/`)

Accepts multipart form with `meeting`, `file`, and optional `dryrun`. File is parsed by `detect_and_parse_file` (auto-detects XLSX, ODS, CSV, TSV by content). A `roles` column in the file sets per-row roles; rows without it default to PARTICIPANT. Annotation columns (`group`, `grouprole`) are processed after invite creation. Same response shape as the JSON endpoint.

## Shared helpers (`serializers.py`)

- `_raise_if_conflicting_partials(meeting, items)` — called before `create_or_update_mixed`; raises `ValidationError` if any incoming identity values partially match different DB invites (e.g. `email` matches one invite, `ssn` matches another). Used by both the JSON serializer and the file import view.
- `_raise_if_moderator_lockout(meeting, items, roles)` — raises `ValidationError` with affected userids if the new roles would downgrade an existing moderator. Used by both paths.
- `_items_to_columns(items, reg)` — builds a stable, constraint-satisfying column list from a list of dicts.

## Serializers

- `InviteCreateSerializer` — JSON create/annotate path. Returns a dict directly from `save()`.
- `InviteImportSerializer` — file upload path; parses the file and validates via `RowColInvitesBaseSchema`.
- `MeetingInviteSerializer` — read-only, includes `has_annotations` (bool). When serializing a queryset, expects it to be pre-annotated via `reg.prep_invites_qs_for_subscribe(qs)`; single-instance serialization fetches live.
- `ExternalMeetingInviteSerializer` — used by both match ViewSets; adds `organisation_host` and `meeting_title` computed fields.
- `InviteBulkSerializer` — validates a list of invite PKs all belong to a specific meeting where the requesting user is moderator.
- `InviteClearAnnotationsSerializer` — validates a list of invite PKs for the `clear-annotations` action.
- `InviteQuerySerializer` — deserializes scope+data pairs for the match endpoint.

## Key constraints

- `bulk-delete` and `bulk-revoke` require the `meeting` field in the POST body; the serializer validates all invite PKs belong to that meeting.
- Neither `accept` nor `reject` on `HandleMatchedInvitesViewSet` uses the rules permission system — access control is purely via queryset scoping.
- `MeetingInviteViewSet.list` intentionally returns an empty list (`[]`); invites are delivered over WebSocket via `MeetingInvitesChannel`, not polled.
