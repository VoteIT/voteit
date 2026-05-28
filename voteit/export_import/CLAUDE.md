# export_import

Exports and imports meeting structure (agenda items, proposals, discussions, groups, reactions, notes) as signed YAML files. Used for meeting templates, cloning, and data portability.

## Tests

```bash
python manage.py test voteit.export_import --keepdb --failfast
```

Test fixtures live in `tests/fixtures/` — key ones: `combined_meeting_fixture.yaml` (full-featured), `ais_and_groups.yaml` (used in doctests), `bad_signature.yaml` and `empty_sign.yaml`. All signed fixtures use HMAC-SHA256 with `EXPORT_SECRET_KEY="abcdefghijk"` for tests.

Note: `empty_sign.yaml` has a deliberately empty signature — it passes the validator (tiny file) and fails later with "no agenda items or groups", not a signature error.

## Key files

- `exporter.py` — `Exporter`: converts `Meeting` → `ExportMeetingStructure` via Pydantic ORM mode
- `importer.py` — `Importer`: parses YAML → schema → creates/updates DB objects; call `.run()` (or `importer()`) after `from_file()` / `from_stream()`
- `schemas.py` — Pydantic v1 schemas for all entities; context-aware validators control filtering; HTML sanitization on every text field
- `utils.py` — HMAC-SHA256 signing/verification, `_NoAliasLoader`, `MAX_IMPORT_BYTES`, `MAX_UNSIGNED_IMPORT_BYTES`, `direct_clone()`
- `exceptions.py` — `ImportFileError`, `SignatureVerificationFailed`
- `rest_api/views.py` — `MeetingDataViewSet`: `GET /yaml/`, `POST /preview/`, `PUT /`, `POST /clone/`
- `rest_api/serializers.py` — `ImportFileSerializer`, `ExportFileSerializer`, `ImportFileValidator` (size + signature check only)
- `rest_api/lock.py` — `acquire_import_lock`, `release_import_lock`: per-session Redis lock preventing duplicate/concurrent imports
- `management/commands/` — CLI: `export_meeting_structure`, `import_meeting_structure`, `import_signature_check`

## Non-obvious design decisions

### Context variables for schema filtering
All `include_*` / `clear_*` flags are passed through a `ContextVar` (`schema_context_vars`), not as constructor args to schemas. The `schema_context(**kwargs)` context manager sets this; Pydantic validators read it at validation time. This is how `Exporter(**kwargs)` and `Importer(**kwargs)` propagate options into deeply nested schemas without threading args everywhere.

### PK masking
Integer PKs in exports are prefixed with `_` (e.g., `_123`) to mark them as placeholder IDs. On import they must be remapped — never used directly as DB PKs.

### Pydantic v1
The project pins Pydantic `<2`. Use `.from_orm()`, `@validator`, `class Config: orm_mode = True`. Do not use v2 syntax (`model_validator`, `field_validator`, `model_config`, etc.).

### Signing: HMAC-SHA256, quality indicator only
`sign_payload()` uses `hmac.new(key, payload, "sha256")`. Signing is a **quality indicator** — it signals the file came from a VoteIT export, not arbitrary YAML. It is not an access-control boundary. `EXPORT_SECRET_KEY` (>10 chars) must be set in Django settings. If missing or short, `apps.ready()` logs a warning; `ValueError` is raised lazily by `get_export_secret()` when actually needed. Verification uses `secrets.compare_digest()` to prevent timing attacks.

### YAML alias bomb protection
`importer.py` uses `_NoAliasLoader` (defined in `utils.py`) instead of `yaml.safe_load()`. It's a `SafeLoader` subclass that raises `ImportFileError` if the input contains any YAML anchor/alias — preventing exponential memory expansion from crafted inputs.

### Tiered upload size cap
Two limits live in `utils.py`:
- `MAX_IMPORT_BYTES = 2 MB` — hard ceiling; always enforced regardless of signature
- `MAX_UNSIGNED_IMPORT_BYTES = 300 KB` — applied to files whose signature is absent or invalid

`ImportFileValidator` checks the hard ceiling first, then attempts signature verification. If the signature is invalid it falls back to the smaller limit. Either way it sets `value._signature_valid` (bool) on the file object so the view can read it without re-running `verify_stream`.

### Validator splits from view
`ImportFileValidator` in `serializers.py` handles size and signature only — it does **not** run the full Pydantic schema validation. Full validation (schema, version check, flag combinations) happens in the view via `Importer.from_stream()`. Both `update()` and `preview()` catch `ImportFileError`, `SignatureVerificationFailed`, and `ReaderError` and return `400`. Both pass `verify=False` to `Importer` (no double-parse — the validator already verified).

### Preview response includes signature metadata
`POST /preview/` returns the parsed structure plus two extra fields:
- `signature_valid: bool` — whether the uploaded file had a valid VoteIT signature
- `size_limit: int` — the applicable byte limit (`MAX_IMPORT_BYTES` if signed, `MAX_UNSIGNED_IMPORT_BYTES` if not); intended for the frontend to display the current threshold to the user

### HTML sanitization in schemas
Every user-supplied text field in `schemas.py` is sanitized on import:
- **Plain-text fields** (titles, descriptions, icon, color, note intent): `strip_html()` — all markup removed
- **Rich-text body fields** (proposals, discussions, agenda items, groups, notes): `strict_clean_html()` — safe tags preserved, dangerous tags/attributes stripped
- **TextDocument body**: `strip_html()` — the document text is plaintext, no HTML allowed

Sanitization happens in Pydantic `@validator` methods (with `pre=True`) before the data reaches the model layer. Model-level `RichTextField` cleaners then act as a second pass.

### Synchronous import
`PUT /meeting-data/{id}/` validates and runs `importer.run()` inside `transaction.atomic(durable=True)`, returning `200 OK` + the stats dict. Import is fully synchronous in the request thread.

### Per-session import lock
`rest_api/lock.py` guards `update()`, `preview()`, and `clone()` against duplicate/concurrent submissions. Two Redis cache keys are used per session:

- `meeting_data:processing:{session_key}` — held for up to 120 s while a request is running; acquired via `cache.add()` (atomic). Returns `409 Conflict` if already set.
- `meeting_data:cooldown:{session_key}` — set for 5 s immediately after the processing key is released (in a `finally` block). Returns `429 Too Many Requests` if set.

The lock is acquired **after** `serializer.is_valid()` and source/target validation so ordinary validation errors bypass the lock entirely and never start a cooldown. All three endpoints share the same lock keys, so an in-flight import blocks a clone and vice versa.

### Clone endpoint
`POST /meeting-data/{pk}/clone/` clones meeting structure from a source meeting into the target meeting (the `pk` in the URL). Accepts JSON (uses `JSONParser` in addition to `MultiPartParser`). The target must be in `upcoming` state. The caller must be moderator of both the source and target meetings. Body: `{"source": <meeting_pk>, ...include/clear flags...}`. Returns the same stats dict as `PUT /`.

### model_to_schema registry
`schemas.py` contains a `model_to_schema` dict mapping Django models → Pydantic schemas. This enables polymorphic serialization (e.g., `Proposal` vs `DiffProposal` use different schemas).

### direct_clone()
Wraps export+import in a single atomic transaction. Used by the Meeting admin action to clone meetings. Signature: `direct_clone(*, source: Meeting, target: Meeting, dry_run=True, **kwargs) -> Importer`.

`dry_run=True` is the default — the transaction rolls back after running (preview/test mode). Pass `dry_run=False` to persist changes. The admin form's `commit` boolean is inverted at the call site: `dry_run=not commit`.

## REST API parameters

**Include/exclude data:**
`include_groups`, `include_proposals`, `include_discussions`, `include_buttons`, `include_reactions`

Note: `include_reactions` defaults to `False` (opt-in). All others default to `True`.

**Clear data on export:**
`clear_authors`, `clear_group_authors`, `clear_ai_states`, `clear_proposal_states`, `clear_proposal_id`

**Import behaviour:**
`use_existing_groups` (update_or_create by groupid), `add_participants` (auto-add imported users as participants)

## MissingUser strategies

When a username in the YAML doesn't exist in the target DB:
- `MissingUser.RAISE` (default) — raises `User.DoesNotExist`
- `MissingUser.BLANK` — maps to `None` (anonymous)
