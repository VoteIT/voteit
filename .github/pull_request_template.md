## Summary

<!-- What does this PR do? One paragraph is enough. -->

## Motivation

<!-- Why is this change needed? Link any relevant issue with "Closes #N" or "Related to #N". -->

## Changes

<!-- Bullet list of the notable changes (models, APIs, migrations, config, …). -->

-

## Testing

<!-- How did you verify this? Mention the test modules that cover this, or note if manual testing was needed. -->

## Checklist

- [ ] `make test` and `make test-deps` are green
- [ ] `uv run ruff check voteit/ src/` reports no issues
- [ ] Migrations are included (if models changed)
- [ ] `docs/narrative.md` / `docs/workflows.md` updated (if model behaviour, permissions, or state machines changed)
- [ ] `CHANGELOG.md` entry added
- [ ] New models have `get_additional_data()` for the auditlog and are decorated with `@auditlog.register()`
