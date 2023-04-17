from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING
from django.utils.translation import gettext_lazy as _
from django.utils.functional import classproperty
from pydantic import BaseModel
from django.db import models

if TYPE_CHECKING:
    from voteit.invites.models import MeetingInvite


class InviteDataAdapter(ABC):
    @property
    @abstractmethod
    def name(cls) -> str:
        """
        ID-like name and namespace. Keep it short!
        """
        # with suppress(AttributeError):
        #     return cls.__name
        # assert issubclass(cls.schema, BaseModel), "Must be a pydantic BaseModel"
        # props = cls.schema.schema()["properties"]
        # assert len(props) == 1, "Must have exactly one named field"
        # cls.__name = tuple(props.keys())[0]
        # return cls.__name

    @classproperty
    def title(self) -> str | _:
        return self.name.title()

    @classproperty
    def columns(cls) -> list[str]:
        """
        When imported, what kind of header does this column have? Does it span over several fields?
        """
        return [cls.name]

    # @classproperty
    @property
    @abstractmethod
    def schema(self) -> type[BaseModel]:
        ...

    @classmethod
    def from_cols(cls, *cols: str) -> BaseModel:
        if len(cols) != len(cls.columns):
            raise ValueError(
                f"Must have exactly {len(cls.columns)} positional arguments"
            )
        return cls.schema(**dict(zip(cls.columns, cols)))

    @classmethod
    def query(cls, *values) -> models.Q:
        return models.Q(**{f"user_data__{cls.name}__in": values})


# class InviteDispatcher(ABC):
#     @property
#     @abstractmethod
#     def name(self) -> str:
#         """
#         ID-like name of this dispatching strategy.
#         """
#
#     @property
#     @abstractmethod
#     def type(self) -> str:
#         """
#         Which type does this handle?
#         """
#
#     @property
#     @abstractmethod
#     def title(self) -> str:
#         """
#         Human-readable title
#         """
#
#     def __init__(self, dispatch: InviteDispatch):
#         self.dispatch = dispatch
#
#     @abstractmethod
#     def send(self, invite: MeetingInvite) -> bool:
#         """
#         Send the invite, return success state
#         """
