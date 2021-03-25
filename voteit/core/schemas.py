from __future__ import annotations

from random import choices
from string import ascii_letters
from string import digits
from typing import List
from typing import Optional
from typing import Set

from pydantic import BaseModel
from pydantic import validator


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
    context: Set[str]

    class Config:
        orm_mode = True


RoleOutput.update_forward_refs()


_chars = ascii_letters + digits


def generate_session_id(size=30) -> str:
    return "".join(choices(_chars, k=size))


class OAuthStateSchema(BaseModel):
    state: str = generate_session_id()
    provider_pk: int
    next: str = "/"

    @validator("next")
    def validate_next(cls, v):
        # FIXME: Proper validation
        if not v.startswith("/"):
            raise ValueError("Must start with /")
        return v
