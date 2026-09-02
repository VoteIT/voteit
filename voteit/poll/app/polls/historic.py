import json
from abc import ABC

from pydantic import ConfigDict, BaseModel
from voteit.poll.abcs import PollMethod
from voteit.poll.abcs import vote_json
from voteit.poll.app.polls.schulze import Schulze
from voteit.poll.app.polls.schulze import SchulzeVoteSchema
from voteit.poll.registries import poll_methods


class HistoricSettingsData(BaseModel):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class HistoricVoteData(BaseModel):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class HistoricResultData(BaseModel):
    approved: list = []
    denied: list = []
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class HistoricPollMethod(PollMethod, ABC):
    historic = True
    vote_schema = HistoricVoteData
    result_schema = HistoricResultData
    settings_schema = HistoricSettingsData

    def _die(self, *args):
        raise ValueError("Historic methods can't be used")

    calculate_result = validate_vote = start_check = _die


class HistoricWithVoteData(HistoricPollMethod, ABC):
    def vote_to_str(self, data: BaseModel) -> str:
        """
        >>> class SomeMethod(HistoricWithVoteData):
        ...     name = 'dummy'
        ...
        >>> data = HistoricVoteData(what=1, ever='we', want=False)
        >>> text = SomeMethod(None).vote_to_str(data)
        >>> '"what": 1' in text
        True
        >>> '"want": false' in text
        True
        >>> '"ever": "we"' in text
        True
        """
        return vote_json(data)

    def vote_to_obj(self, text: str) -> BaseModel:
        """
        >>> class SomeMethod(HistoricWithVoteData):
        ...     name = 'dummy'
        ...
        >>> text = '{"what": 1, "ever": "we", "want": false}'
        >>> data = SomeMethod(None).vote_to_obj(text)
        >>> [(k, getattr(data, k)) for k in sorted(data.model_dump().keys())]
        [('ever', 'we'), ('want', False), ('what', 1)]
        """
        return self.vote_schema(**json.loads(text))


class HistoricSchulzeMethod(HistoricPollMethod, Schulze):
    vote_schema = SchulzeVoteSchema


@poll_methods
class SchulzePR(HistoricSchulzeMethod):
    name = "schulze_pr"


@poll_methods
class SchulzeSTV(HistoricSchulzeMethod):
    name = "schulze_stv"
