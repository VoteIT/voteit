from rest_framework import fields
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from voteit.export_import.exceptions import SignatureVerificationFailed
from voteit.export_import.utils import MAX_IMPORT_BYTES
from voteit.export_import.utils import verify_stream


class ImportFileValidator:
    requires_context = False

    def __call__(self, value):
        if value.size > MAX_IMPORT_BYTES:
            raise ValidationError(
                f"File too large (max {MAX_IMPORT_BYTES // (1024 * 1024)} MB)"
            )
        try:
            verify_stream(value)
        except SignatureVerificationFailed:
            raise ValidationError(
                "Signature isn't valid for this file.", code="invalid_sign"
            )
        value.seek(0)  # Reset!


class ImportFileSerializer(serializers.Serializer):
    """
    Pass along args to importer

    Compare context arg with serializer args
    >>> from voteit.export_import.schemas import BaseContext
    >>> schema_fields = set(BaseContext.schema()['properties'])
    >>> _ = [schema_fields.remove(x) for x in {'model_to_schema', 'include_notes'}]
    >>> serializer = ImportFileSerializer()
    >>> ser_fields = set(serializer.fields)
    >>> _ = [ser_fields.remove(x) for x in {'file', 'add_participants'}] # Not in schema

    >>> schema_fields - ser_fields
    set()
    """

    file = fields.FileField(max_length=1000000, validators=[ImportFileValidator()])
    add_participants = fields.BooleanField()
    use_existing_groups = fields.BooleanField(default=True)
    clear_group_authors = fields.BooleanField()
    clear_authors = fields.BooleanField()
    clear_ai_states = fields.BooleanField()
    clear_proposal_states = fields.BooleanField()
    clear_proposal_id = fields.BooleanField()
    include_groups = fields.BooleanField(default=True)
    include_proposals = fields.BooleanField(default=True)
    include_discussions = fields.BooleanField(default=True)
    include_buttons = fields.BooleanField(default=True)
    include_reactions = fields.BooleanField(default=False)


class ExportFileSerializer(serializers.Serializer):
    clear_group_authors = fields.BooleanField(default=False)
    clear_authors = fields.BooleanField(default=False)
    clear_ai_states = fields.BooleanField(default=False)
    clear_proposal_states = fields.BooleanField(default=False)
    clear_proposal_id = fields.BooleanField(default=False)
    include_groups = fields.BooleanField(default=True)
    include_proposals = fields.BooleanField(default=True)
    include_discussions = fields.BooleanField(default=True)
    include_buttons = fields.BooleanField(default=True)
    include_reactions = fields.BooleanField(default=False)
    # Don't allow notes here!
