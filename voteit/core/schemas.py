from __future__ import annotations

from typing import List
from typing import Optional

from pydantic import validator
from pydantic.main import BaseModel


class RoleOutput(BaseModel):
    name: str
    title: str
    description: str
    require_names: Optional[List[str]]
    roles_cls_natural_key: Optional[str]
    context_natural_key: Optional[str]
    predicate_info: Optional[PredicateOutput]

    class Config:
        orm_mode = True


class PredicateOutput(BaseModel):
    name: str
    description: Optional[str]
    fullname: str = ""
    num_args: int
    source: str = ""
    role_name: Optional[str]

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
    model: Optional[str]
    context: Optional[str]

    class Config:
        orm_mode = True


RoleOutput.update_forward_refs()
