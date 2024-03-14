from rest_framework import fields
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from yaml.reader import ReaderError

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
        if not (importer.data.groups or importer.data.agenda_items):
            raise ValidationError("File doesn't contain any agenda items or groups")
        value.seek(0)  # Reset!


class ImportFileSerializer(serializers.Serializer):
    file = fields.FileField(max_length=1000000, validators=[ImportFileValidator()])
    commit = fields.BooleanField(default=False)


class ExportFileSerializer(serializers.Serializer):
    clear_group_authors = fields.BooleanField(default=False)
    clear_authors = fields.BooleanField(default=False)
    clear_ai_states = fields.BooleanField(default=False)
    clear_proposal_states = fields.BooleanField(default=False)
    clear_proposal_id = fields.BooleanField(default=False)
    include_groups = fields.BooleanField(default=True)
    include_proposals = fields.BooleanField(default=True)
    include_discussions = fields.BooleanField(default=True)
