from rest_framework import fields
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from yaml.reader import ReaderError
from pydantic import ValidationError as PydanticValidationError

from voteit.core.rest_api.utils import pydantic_to_drf_validation_error
from voteit.export_import.exceptions import SignatureVerificationFailed
from voteit.meeting.models import Meeting
from voteit.export_import.importer import ImportFileError
from voteit.export_import.importer import Importer


class ImportFileValidator:
    requires_context = True

    def __call__(self, value, serializer_field):
        meeting: Meeting = serializer_field.context["meeting"]
        importer = Importer(meeting)
        try:
            importer.from_stream(value)
        except ReaderError as exc:
            raise ValidationError("Not a valid yaml file")
        except ImportFileError as exc:
            raise ValidationError(exc)
        except PydanticValidationError as exc:
            raise pydantic_to_drf_validation_error(exc)
        except SignatureVerificationFailed:
            raise ValidationError(
                "Signature isn't valid for this file.", code="invalid_sign"
            )
        if not (importer.data.groups or importer.data.agenda_items):
            raise ValidationError("File doesn't contain any agenda items or groups")
        value.seek(0)  # Reset!


class ImportFileSerializer(serializers.Serializer):
    """
    Pass along args to importer

    Compare context arg with serializer args
    >>> from voteit.export_import.schemas import BaseContext
    >>> schema_fields = set(BaseContext.schema()['properties'])
    >>> _ = schema_fields.remove('model_to_schema')

    >>> serializer = ImportFileSerializer()
    >>> ser_fields = set(serializer.fields)
    >>> _ = ser_fields.remove('file'), ser_fields.remove('add_participants')  # Not in schema

    >>> schema_fields - ser_fields
    set()
    """

    file = fields.FileField(max_length=1000000, validators=[ImportFileValidator()])
    add_participants = fields.BooleanField()
    clear_group_authors = fields.BooleanField()
    clear_authors = fields.BooleanField()
    clear_ai_states = fields.BooleanField()
    clear_proposal_states = fields.BooleanField()
    clear_proposal_id = fields.BooleanField()
    include_groups = fields.BooleanField(default=True)
    include_proposals = fields.BooleanField(default=True)
    include_discussions = fields.BooleanField(default=True)


class ExportFileSerializer(serializers.Serializer):
    clear_group_authors = fields.BooleanField(default=False)
    clear_authors = fields.BooleanField(default=False)
    clear_ai_states = fields.BooleanField(default=False)
    clear_proposal_states = fields.BooleanField(default=False)
    clear_proposal_id = fields.BooleanField(default=False)
    include_groups = fields.BooleanField(default=True)
    include_proposals = fields.BooleanField(default=True)
    include_discussions = fields.BooleanField(default=True)
