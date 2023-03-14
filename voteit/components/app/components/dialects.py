from pydantic import BaseModel
from pydantic import conset
from pydantic import constr
from pydantic import validator

from voteit.components.abcs import ComponentAdapter
from voteit.components.registries import organisation_components
from voteit.meeting.utils import get_named_path_dict

__all__ = (
    "DialectsFilterSchema",
    "DialectsFilter",
)


class DialectsFilterSchema(BaseModel):
    include: conset(constr(strip_whitespace=True, to_lower=True)) = []
    exclude: conset(constr(strip_whitespace=True, to_lower=True)) = []

    @validator("include", "exclude")
    def validate_dialect_name(cls, v: set[str]):
        valid_names = set(get_named_path_dict())
        invalid = v - valid_names
        if invalid:
            raise ValueError(f"Doesn't match known dialects: {', '.join(invalid)}")
        return v


@organisation_components
class DialectsFilter(ComponentAdapter):
    name = "dialects_filter"
    title = "Meeting dialects filter"
    schema = DialectsFilterSchema
