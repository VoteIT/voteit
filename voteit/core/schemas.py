from __future__ import annotations

from typing import Any

from django.utils.functional import Promise
from pydantic import field_validator, ConfigDict, BaseModel


class RoleOutput(BaseModel):
    name: str
    title: str
    description: str
    require_names: list[str] | None = None
    predicate_info: PredicateOutput | None = None
    model_config = ConfigDict(from_attributes=True)

    @field_validator("title", "description", mode="before")
    @classmethod
    def convert_lazy(cls, v: Any):
        if isinstance(v, Promise):
            return str(v)
        return v


class PredicateOutput(BaseModel):
    name: str
    description: str | None = None
    fullname: str = ""
    num_args: int
    source: str = ""
    role_name: str | None = None

    @field_validator("description")
    @classmethod
    def clean_description(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v

    model_config = ConfigDict(from_attributes=True)


class PermissionOutput(BaseModel):
    name: str
    description: str = ""
    model: str | None = None
    context: set[str]
    model_config = ConfigDict(from_attributes=True)


RoleOutput.model_rebuild()
