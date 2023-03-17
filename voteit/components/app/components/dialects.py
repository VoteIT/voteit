from pydantic import BaseModel
from pydantic import conlist
from pydantic import constr
from pydantic import validator

from voteit.components.abcs import ComponentAdapter
from voteit.components.registries import organisation_components


__all__ = (
    "DialectsFilterSchema",
    "DialectsFilter",
)


class DialectsFilterSchema(BaseModel):
    include: conlist(
        constr(strip_whitespace=True, to_lower=True), unique_items=True
    ) = []
    exclude: conlist(
        constr(strip_whitespace=True, to_lower=True), unique_items=True
    ) = []

    @validator("include", "exclude")
    def validate_dialect_name(cls, v: list[str]):
        from voteit.meeting.dialects import get_named_path_dict  # Avoid circular

        valid_names = set(get_named_path_dict())
        invalid = set(v) - valid_names
        if invalid:
            raise ValueError(f"Doesn't match known dialects: {', '.join(invalid)}")
        return v


@organisation_components
class DialectsFilter(ComponentAdapter):
    name = "dialects_filter"
    title = "Meeting dialects filter"
    schema = DialectsFilterSchema
