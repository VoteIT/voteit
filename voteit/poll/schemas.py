from typing import Any, Optional

from pydantic.main import BaseModel


class GenericVoteSchema(BaseModel):
    vote: Any  # Override this
    abstain: bool = False
    pk: int  # Poll pk for votes
