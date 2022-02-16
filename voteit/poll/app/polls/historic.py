from abc import ABC

from pydantic import BaseModel
from voteit.poll.abcs import PollMethod
from voteit.poll.registries import poll_methods


class HistoricPollData(BaseModel):
    class Config:
        extra = "allow"
        arbitrary_types_allowed = True


class HistoricPollMethod(PollMethod, ABC):
    historic = True
    vote_schema = HistoricPollData
    result_schema = HistoricPollData
    settings_schema = HistoricPollData

    def _die(self, *args):
        raise ValueError("Historic methods can't be used")

    calculate_result = validate_vote = start_check = vote_to_obj = vote_to_str = _die


@poll_methods
class SchulzePR(HistoricPollMethod):
    name = "schulze_pr"


@poll_methods
class SchulzeSTV(HistoricPollMethod):
    name = "schulze_stv"
