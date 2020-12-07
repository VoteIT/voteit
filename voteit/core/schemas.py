from __future__ import annotations

from pydantic import validator
from pydantic.main import BaseModel
from typing import Optional, List


class RoleOutput(BaseModel):
    name: str
    title: str
    description: str
    require_names: Optional[List[str]]
    roles_cls_name: Optional[str]
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
    model_name: Optional[str]

    class Config:
        orm_mode = True


RoleOutput.update_forward_refs()
