# proposal

Manages proposals (motions/amendments) within meeting agenda items. Supports regular text proposals and diff proposals (amendments to a reference document). Handles state transitions, permission checks, WebSocket broadcasting, CSV/JSON export, and pluggable proposal-ID generation.

## Tests

```bash
python manage.py test voteit.proposal --keepdb --failfast
```

## Key files

- `models.py` — `Proposal`, `DiffProposal` (MTI), `TextDocument`, `TextParagraph`; FSM transitions live here as methods
- `workflows.py` — `ProposalWf`: states PUBLISHED / RETRACTED / VOTING / APPROVED / DENIED / UNHANDLED
- `rules.py` — django-rules permission predicates for ADD / CHANGE / DELETE / RETRACT
- `signals.py` — post-save/pre-delete handlers that broadcast to ParticipantsChannel and ModeratorsChannel
- `messages.py` — `ProposalAdded`, `ProposalChanged`, `ProposalDeleted`, `TextDocumentAdded/Changed/Deleted` WebSocket messages
- `diff.py` — `Changes` class: word-level HTML diff between original and amended text
- `app/proposal_id/userid.py` — `UseridPID`: default proposal-ID policy (e.g. `"john-doe-1"`)
- `registries.py` — `proposal_id_registry`: Registry instance for ProposalIDPolicy plugins
- `rest_api/views.py` — `ProposalViewSet`, `TextDocumentViewSet`, `ExportProposalsViewSet`
- `rest_api/serializers.py` — Morphic serializer pattern for Proposal vs DiffProposal

## Non-obvious design decisions

### Multi-table inheritance + InheritanceManager
`DiffProposal` extends `Proposal` via Django MTI. Querysets call `.select_subclasses()` (django-model-utils `InheritanceManager`) to return concrete types. The morphic serializer then dispatches to the right DRF serializer at runtime based on `get_model_shortname(instance)`.

### Morphic serializers
`GenericProposalSerializer` and `GenericCreateProposalSerializer` override `__new__` to swap themselves with the correct concrete serializer chosen from a registry keyed by shortname (`"proposal"` or `"diff_proposal"`). Do not use them with `many=True`.

### Proposal-ID policy (pluggable)
`Proposal.save()` calls `meeting.pid_policy` (a string) to look up a `ProposalIDPolicy` instance from `proposal_id_registry`. The default `UseridPID` produces `"username-1"`, `"username-2"`, etc. Implement `abcs.ProposalIDPolicy` and decorate with `@proposal_id_registry` to add new policies. The constant `DEFAULT_PROPOSAL_ID_POLICY = "userid"` lives in `__init__.py`.

### prop_id is always added to tags
`Proposal.save()` ensures `prop_id` appears in the `tags` list. This is how proposals can be cross-referenced by tag from other content.

### FSM transitions carry permission guards
Transitions such as `retract()`, `lock_for_vote()`, `approved()`, `denied()` check permissions inside the transition decorator (not only at the API layer). The `RETRACT` permission string is exposed as `PERM_RETRACT = "retract"` in `__init__.py`.

### Signal-driven WebSocket broadcasting
`signals.py` uses post_save / pre_delete signals to publish to envelope channels. `attach_proposals()` bundles proposals into `Batch` messages on channel subscribe (efficient initial load). Private agenda items are only sent to ModeratorsChannel. `@disable_on_raw_save` prevents broadcasts during data migrations.

### TextDocument + TextParagraph lifecycle
`TextDocument.save()` is wrapped in `transaction.atomic()` and calls `create_text_paragraphs()` to split body on double newlines. `TextParagraph.tag` = `"{base_tag}-{paragraph_id}"`. A DiffProposal references a single `TextParagraph` — you cannot edit or delete a `TextDocument` that already has diff proposals (enforced by the `has_no_proposals` predicate on CHANGE/DELETE of TextDocument).
