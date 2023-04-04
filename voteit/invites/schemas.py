from pydantic import BaseModel
from pydantic import root_validator


class CombinedInviteSchema(BaseModel):
    """
    This will be combined with other validation schemas. But they must exist.
    >>> CombinedInviteSchema(one=1)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 1 validation error for CombinedInviteSchema
    __root__
      At least one value required (type=value_error)
    """

    @root_validator
    def at_least_one(cls, values: dict):
        for v in values.values():
            if v:
                return values
        raise ValueError("At least one value required")
