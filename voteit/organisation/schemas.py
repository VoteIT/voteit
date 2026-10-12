from typing import Annotated

from django.core.exceptions import ValidationError
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import ValidationError as PydanticValidationError

_Channel = Annotated[int, Field(ge=0, le=255, strict=True)]


class RGB(BaseModel):
    model_config = ConfigDict(extra="forbid")

    r: _Channel
    g: _Channel
    b: _Channel


class OrganisationColors(BaseModel):
    """Stored as-is in ``Organisation.colors``, keys are what the SPA uses."""

    model_config = ConfigDict(extra="forbid")

    appBar: RGB | None = None


def validate_colors(value):
    if not isinstance(value, dict):
        raise ValidationError("Must be an object")
    try:
        OrganisationColors.model_validate(value)
    except PydanticValidationError as exc:
        raise ValidationError(
            [
                f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
                for err in exc.errors()
            ]
        )
