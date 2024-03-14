from datetime import datetime

from django.utils.timezone import now
from pydantic import BaseModel
from pydantic import ConfigError

from voteit.meeting.models import Meeting
from voteit.export_import.schemas import MeetingStructure
from voteit.export_import.schemas import schema_context

__all__ = (
    "ExportMeetingMeta",
    "ExportMeetingStructure",
    "Exporter",
)


class ExportMeetingMeta(BaseModel):
    version: int = 1
    created: datetime = now()
    title: str = ""
    description: str = ""


class ExportMeetingStructure(MeetingStructure):
    meta: ExportMeetingMeta | None


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
        if not schema.__config__.orm_mode:
            raise ConfigError("orm_mode must be set to use schema with exporter")
        self.schema = schema
        self.title = title
        self.description = description
        self.export_schema_kwargs = kwargs

    def __call__(self):
        with schema_context(**self.export_schema_kwargs):
            self.data = self.schema.from_orm(self.meeting)
        self.data.meta = ExportMeetingMeta(
            title=self.title or self.meeting.title,
            description=self.description,
            version=self.version,
        )
