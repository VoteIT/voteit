from __future__ import annotations

from pydantic import BaseModel
from pydantic import validator


class RoleOutput(BaseModel):
    name: str
    title: str
    description: str
    require_names: list[str] | None
    predicate_info: PredicateOutput | None

    class Config:
        orm_mode = True


class PredicateOutput(BaseModel):
    name: str
    description: str | None
    fullname: str = ""
    num_args: int
    source: str = ""
    role_name: str | None

    @validator("description")
    def clean_description(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v

    class Config:
        orm_mode = True


class PermissionOutput(BaseModel):
    name: str
    description: str = ""
    model: str | None
    context: set[str]

    class Config:
        orm_mode = True


RoleOutput.update_forward_refs()
