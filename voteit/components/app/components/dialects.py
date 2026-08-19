from pydantic import field_validator, Field, StringConstraints, BaseModel

from voteit.core.validators import ensure_unique
from voteit.components.abcs import ComponentAdapter
from voteit.components.registries import organisation_components
from typing import List
from typing_extensions import Annotated


__all__ = (
    "DialectsFilterSchema",
    "DialectsFilter",
)


class DialectsFilterSchema(BaseModel):
    include: Annotated[
        List[Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True)]],
        Field(),
    ] = []
    exclude: Annotated[
        List[Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True)]],
        Field(),
    ] = []

    @field_validator("include", "exclude")
    @classmethod
    def validate_dialect_name(cls, v: list[str]):
        ensure_unique(v)
        from voteit.meeting.dialects import get_named_paths  # Avoid circular

        valid_names = {k for k, v in get_named_paths()}
        invalid = set(v) - valid_names
        if invalid:
            raise ValueError(f"Doesn't match known dialects: {', '.join(invalid)}")
        return v


@organisation_components
class DialectsFilter(ComponentAdapter):
    name = "dialects_filter"
    title = "Meeting dialects filter"
    schema = DialectsFilterSchema
