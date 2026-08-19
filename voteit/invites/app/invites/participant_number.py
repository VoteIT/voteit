from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import field_validator, Field
from pydantic.main import BaseModel
from typing_extensions import Annotated


if TYPE_CHECKING:
    pass


class ParticipantNumberSchema(BaseModel):
    pn: Annotated[int, Field(ge=1, le=999)] | None = None

    @field_validator("pn", mode="before")
    @classmethod
    def cleanup(cls, v):
        if isinstance(v, str):
            return v.strip() or None
        return v


# @invite_adapter_registry
# class ParticipantNumber(AnnotationDataAdapter):
#     """
#     >>> data = [['1'], [' '], [2]]
#     >>> ParticipantNumber.preflight([ParticipantNumber.name], data)
#     >>> data
#     [[1], [None], [2]]
#     """
#
#     name = "pn"
#     schema = ParticipantNumberSchema
#     title = _("Participant number")
#
#     def accepted(self):
#         ...
#
#     @classmethod
#     def annotate(
#         cls,
#         **kwargs
#         # *,
#         # invites_qs: QuerySet[MeetingInvite],
#         # columns: list[str],
#         # rows: list[list[str | None | int]],
#     ):
#         ...
#
#     @classmethod
#     def clear(cls, meeting: Meeting) -> models.QuerySet[MeetingInvite]:
