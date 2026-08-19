from voteit.export_import.schemas import ExportMeetingStructure
from voteit.meeting.models import Meeting
from voteit.export_import.schemas import schema_context

__all__ = ("Exporter",)


class Exporter:
    version = 1

    def __init__(
        self,
        meeting: Meeting,
        title: str = "",
        description: str = "",
        schema: type[ExportMeetingStructure] = ExportMeetingStructure,
        **kwargs,
    ):
        self.meeting = meeting
        if not schema.model_config.get("from_attributes"):
            raise TypeError("from_attributes must be set to use schema with exporter")
        self.schema = schema
        self.title = title
        self.description = description
        self.export_schema_kwargs = kwargs

    def __call__(self):
        with schema_context(**self.export_schema_kwargs):
            self.data = self.schema.model_validate(self.meeting)
        self.data.meta.title = self.title or self.meeting.title
        self.data.meta.description = self.description
        self.data.meta.version = self.version
