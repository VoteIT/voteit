# export_import

Exports and imports meeting structure (agenda items, proposals, discussions, groups, reactions, notes) as signed YAML files. Used for meeting templates, cloning, and data portability.

## Tests

```bash
python manage.py test voteit.export_import --keepdb --failfast
```

Test fixtures live in `tests/fixtures/` — key ones: `combined_meeting_fixture.yaml` (full-featured), `ais_and_groups.yaml` (used in doctests), `bad_signature.yaml` and `empty_sign.yaml` (signature rejection). All signed fixtures use HMAC-SHA256 with `EXPORT_SECRET_KEY="abcdefghijk"` for tests.

## Key files

- `exporter.py` — `Exporter`: converts `Meeting` → `ExportMeetingStructure` via Pydantic ORM mode
- `importer.py` — `Importer`: parses YAML → schema → creates/updates DB objects; call `.run()` (or `importer()`) after `from_file()` / `from_stream()`
- `schemas.py` — Pydantic v1 schemas for all entities; context-aware validators control filtering
- `utils.py` — HMAC-SHA256 signing/verification, `_NoAliasLoader`, `MAX_IMPORT_BYTES`, `direct_clone()`
- `exceptions.py` — `ImportFileError`, `SignatureVerificationFailed`
- `rest_api/views.py` — `MeetingDataViewSet`: `GET /yaml/`, `POST /preview/`, `PUT /`
- `rest_api/serializers.py` — `ImportFileSerializer`, `ExportFileSerializer`, `ImportFileValidator` (size + signature check only)
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

### Upload size cap
`MAX_IMPORT_BYTES = 2 MB` in `utils.py`. `ImportFileValidator` checks `value.size` before attempting to parse. DRF's `FileField(max_length=...)` is filename length only and does not cap file size.

### Validator splits from view
`ImportFileValidator` in `serializers.py` only verifies the signature and file size — it does **not** run the full Pydantic schema validation. Full validation (schema, version check, flag combinations) happens in the view via `Importer.from_stream()`. Both `update()` and `preview()` catch `ImportFileError`, `SignatureVerificationFailed`, and `ReaderError` and return `400`.

### Synchronous import
`PUT /meeting-data/{id}/` validates and runs `importer.run()` inside `transaction.atomic(durable=True)`, returning `200 OK` + the stats dict. Import is fully synchronous in the request thread.

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
