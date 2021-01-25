from __future__ import annotations

from abc import abstractmethod, ABC
from logging import getLogger
from typing import TYPE_CHECKING, Optional
from typing import Type

from pydantic.main import BaseModel
from voteit.core.models import ABCModel
from voteit.poll.schemas import PollResult

if TYPE_CHECKING:
    from voteit.poll.models import Poll

logger = getLogger(__name__)


class PollMethod(ABC):
    """ This is a wrapper for polls that handles calculation of the result
        and the implementation of the poll method.
    """
    poll: Poll

    def __init__(self, poll: Poll):
        self.poll = poll

    @property
    @abstractmethod
    def name(self) -> str:
        """ The name of this poll method. It's an attribute on the class
        """

    @property
    @abstractmethod
    def vote_schema(self) -> Type[BaseModel]:
        """ The pydantic schema used to serialize and validate vote data.
        """

    @property
    @abstractmethod
    def result_schema(self) -> Type[PollResult]:
        """ Pydantic result schema.
        """

    @property
    def settings_schema(self) -> Optional[Type[BaseModel]]:
        """ Pydantic settings schema.
        """
        return None

    @abstractmethod
    def vote_to_str(self, data: BaseModel) -> str:
        """ Take a pydantic instance and turn it into a string that will be suitable
            for storage or calculation of vote result.
        """

    @abstractmethod
    def vote_to_obj(self, text: str) -> BaseModel:
        """ Pydantic instance based on vote_schema.
        """

    @abstractmethod
    def calculate_result(self, counter) -> BaseModel:
        """ Takes the counted ballots, calculate the result and store it.
        """

    def start_check(self) -> bool:  # pragma: no cover
        """ Specifics for this poll method except the ones for the base Poll.
            Things like if there's enough proposals to start the poll.
            Raise exceptions for conditions that aren't met.
        """
        return True


class ElectoralRegisterPolicy(ABCModel):
    """ Responsible for handling electoral registers.
    """

    class Meta:
        abstract = True

    @property
    @abstractmethod
    def title(self) -> str:
        pass

    @abstractmethod
    def apply(self, poll: Poll):
        pass
