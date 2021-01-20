from typing import Any

from pydantic.main import BaseModel


class GenericVoteSchema(BaseModel):
    vote: Any  # Override this
    pk: int  # Poll pk for votes
