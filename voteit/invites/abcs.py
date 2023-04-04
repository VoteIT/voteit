from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from contextlib import suppress
from typing import TYPE_CHECKING
from django.utils.translation import gettext_lazy as _
from django.utils.functional import classproperty
from pydantic import BaseModel

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

    @classproperty
    def many(cls) -> bool:
        """
        Does this store a list-like value? Override for more complex forms
        """
        props = cls.schema.schema()["properties"]
        if len(props) == 1:
            for v in props.values():
                return v.get("type") == "array"
        return False

    # many-prop from schema?
    # @classproperty
    @property
    @abstractmethod
    def schema(self) -> type[BaseModel]:
        ...

    @classmethod
    def from_cols(cls, *cols: list[str]):
        if len(cols) != len(cls.columns):
            raise ValueError(
                f"Must have exactly {len(cls.columns)} positional arguments"
            )
        return cls.schema(**dict(zip(cls.columns, cols)))


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
