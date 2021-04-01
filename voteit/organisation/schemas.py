from random import choices
from string import ascii_letters
from string import digits

from pydantic import BaseModel
from pydantic import validator

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
