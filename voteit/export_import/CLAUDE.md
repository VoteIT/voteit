# export_import

Exports and imports meeting structure (agenda items, proposals, discussions, groups, reactions, notes) as signed YAML files. Used for meeting templates, cloning, and data portability.

## Tests

```bash
python manage.py test voteit.export_import --keepdb --failfast
```

Test fixtures live in `tests/fixtures/` — `combined_meeting_fixture.yaml` is the main full-featured one; `bad_signature.yaml` and `empty_sign.yaml` test signature rejection.

## Key files

- `exporter.py` — `Exporter`: converts `Meeting` → `ExportMeetingStructure` via Pydantic ORM mode
- `importer.py` — `Importer`: parses YAML → schema → creates/updates DB objects; call `.run()` after `from_file()` / `from_stream()`
- `schemas.py` — Pydantic v1 schemas for all entities; context-aware validators control filtering
- `utils.py` — SHA256 signing/verification + `direct_clone()` (atomic export→import in one call)
- `exceptions.py` — `ImportFileError`, `SignatureVerificationFailed`
- `jobs.py` — `run_import_job`: RQ job on the `long` queue that runs `importer.run()` asynchronously
- `messages.py` — `ImportCompleted`: outgoing WebSocket message with `meeting` + `stats`; registered via `@outgoing` in `apps.ready()`
- `rest_api/views.py` — `MeetingDataViewSet`: `GET /yaml/`, `POST /preview/`, `PUT /`
- `management/commands/` — CLI: `export_meeting_structure`, `import_meeting_structure`, `import_signature_check`

## Non-obvious design decisions

### Context variables for schema filtering
All `include_*` / `clear_*` flags are passed through a `ContextVar` (`schema_context_vars`), not as constructor args to schemas. The `schema_context(**kwargs)` context manager sets this; Pydantic validators read it at validation time. This is how `Exporter(**kwargs)` and `Importer(**kwargs)` propagate options into deeply nested schemas without threading args everywhere.

### PK masking
Integer PKs in exports are prefixed with `_` (e.g., `_123`) to mark them as placeholder IDs. On import they must be remapped — never used directly as DB PKs.

### Pydantic v1
The project pins Pydantic `<2`. Use `.from_orm()`, `@validator`, `class Config: orm_mode = True`. Do not use v2 syntax (`model_validator`, `field_validator`, `model_config`, etc.).

### Signature format
The YAML file's first line must be `sign: <sha256hex>`. The remainder is the signed payload. `EXPORT_SECRET_KEY` (>10 chars) must be set in Django settings or the app raises `ImproperlyConfigured` at startup. Verification uses `secrets.compare_digest()` to prevent timing attacks.

### model_to_schema registry
`schemas.py` contains a `model_to_schema` dict mapping Django models → Pydantic schemas. This enables polymorphic serialization (e.g., `Proposal` vs `DiffProposal` use different schemas).

### Asynchronous import via RQ
`PUT /meeting-data/{id}/` returns `202 Accepted` + `{"job_id": "..."}`. The file is validated synchronously in the request thread (signature + schema + flag combinations) via `Importer(meeting, **kwargs).from_stream(file)`, but DB writes happen in `run_import_job` on the `long` queue. The job returns the stats dict (stored in RQ's result) and publishes `ImportCompleted` to `ModeratorsChannel`. On failure it publishes `GenericError` from `envelope.messages.errors` and re-raises so RQ logs the error.

### Session-based import lock
`request.session[f"import_job_{meeting.pk}"]` stores the job ID when an import starts. The next PUT checks the RQ job status — if `queued` or `started`, returns `409 Conflict`. The session key is cleared automatically when a new import is accepted after the previous job has finished. Protection is per-user, not per-meeting.

### direct_clone()
Wraps export+import in a single atomic transaction. Used by the Meeting admin action to clone meetings. Signature: `direct_clone(*, source: Meeting, target: Meeting, **kwargs) -> Importer`.

## REST API parameters

**Include/exclude data:**
`include_groups`, `include_proposals`, `include_discussions`, `include_buttons`, `include_reactions`

**Clear sensitive data on export:**
`clear_authors`, `clear_group_authors`, `clear_ai_states`, `clear_proposal_states`, `clear_proposal_id`

**Import behaviour:**
`use_existing_groups` (update_or_create by groupid), `add_participants` (auto-add imported users as participants)

## MissingUser strategies

When a username in the YAML doesn't exist in the target DB:
- `MissingUser.RAISE` (default) — raises `ImportFileError`
- `MissingUser.BLANK` — maps to `None` (anonymous)
