from datetime import datetime
from random import choices
from string import ascii_letters
from string import digits

from pydantic import BaseModel
from pydantic import Field
from pydantic import validator
from typing import List

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


class OAuthTokenSchema(BaseModel):
    access_token: str
    expires_in: int
    token_type: str = Field("Bearer", const=True)  # Only one supported by us!
    scope: List[str]
    refresh_token: str
    expires_at: float

    @validator("expires_at", pre=True)
    def convert_expires_at(cls, v) -> float:
        if isinstance(v, datetime):
            return v.timestamp()
        return v
