from pydantic import ConfigError

from voteit.export_import.schemas import ExportMeetingStructure
from voteit.export_import.utils import sign_payload
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
        sign: bool = True,
        **kwargs,
    ):
        self.meeting = meeting
        if not schema.__config__.orm_mode:
            raise ConfigError("orm_mode must be set to use schema with exporter")
        self.schema = schema
        self.title = title
        self.description = description
        self.export_schema_kwargs = kwargs
        self.sign = sign

    def __call__(self):
        with schema_context(**self.export_schema_kwargs):
            self.data = self.schema.from_orm(self.meeting)
        if self.sign:
            self.data.meta.sign = sign_payload(self.data.json(exclude={"meta"}))
        self.data.meta.title = self.title or self.meeting.title
        self.data.meta.description = self.description
        self.data.meta.version = self.version
