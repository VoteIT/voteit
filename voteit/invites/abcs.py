from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from voteit.invites.models import MeetingInvite


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
