from abc import ABC

from voteit.poll.messages import AddVote
from voteit.poll.schemas import AddRankedVoteSchema


class AddRankedVote(AddVote, ABC):
    schema = AddRankedVoteSchema
    data: AddRankedVoteSchema
