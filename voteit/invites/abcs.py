from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING
from django.utils.translation import gettext_lazy as _
from django.utils.functional import classproperty
from pydantic import BaseModel
from django.db import models

from voteit.invites.exceptions import DataColValidationError

if TYPE_CHECKING:
    from voteit.invites.models import MeetingInvite
    from voteit.meeting.models import Meeting
    from voteit.invites.registries import InviteAdapterRegistry


class InviteDataAdapter(ABC):
    def __init__(self, invite: MeetingInvite):
        self.invite = invite

    @property
    @abstractmethod
    def name(cls) -> str:
        """
        ID-like name and namespace. Right now same as column. Keep it short!
        """

    @property
    @abstractmethod
    def schema(self) -> type[BaseModel]:
        ...

    @classproperty
    def title(self) -> str | _:
        return self.name.title()

    @classmethod
    def check_column_req(cls, columns: list[str]):
        """
        Columns may require other columns. Complain about that here with a validation error
        """

    @classmethod
    def get_colidx(cls, columns: list[str]):
        colidx = []
        for i, colname in enumerate(columns):
            if colname == cls.name:
                colidx.append(i)
        return colidx

    @classmethod
    def preflight(cls, columns: list[str], rows: list[list[str]]):
        """
        Iterate and validate/transform data. This is an initial check that should follow these rules:
        - Don't touch the database - no validation of existing data.
        - Make no assumptions about sync/async.
        - Go through all data before raising DataColValidationError, if needed.
        - Change data in place.
        - Assume the same column may appear several times.
        - Columns names should've been checked.
        - Rows may not have been stripped and empty values may vary in type.
        """
        for i in cls.get_colidx(columns):
            bad_rows = []
            for num, row in enumerate(rows, 1):
                try:
                    rval = row[i]
                except IndexError:
                    continue
                if rval:
                    try:
                        data = cls.schema(**{cls.name: rval})
                    except ValueError as exc:
                        bad_rows.append(num)
                        continue
                    row[i] = getattr(data, cls.name)
            if bad_rows:
                raise DataColValidationError(name=cls.name, index=i + 1, rows=bad_rows)

    @classproperty
    def is_user_data(cls) -> bool:
        return issubclass(cls, InviteUserDataAdapter)

    @classproperty
    def is_annotation(cls) -> bool:
        return issubclass(cls, AnnotationDataAdapter)

    @classmethod
    def get_row_values(
        cls, columns: list[str], rows: list[list[str, None, int]]
    ) -> set[str]:
        """
        >>> class Dummy(InviteDataAdapter):
        ...     name='dummy'
        ...
        >>> sorted(Dummy.get_row_values(['wo', 'dummy'], [[1,'boo'], ["", ""], [None, 'me']]))
        ['boo', 'me']
        """
        vals = set()
        for i in cls.get_colidx(columns):
            for num, row in enumerate(rows, 1):
                try:
                    rval = row[i]
                except IndexError:
                    continue
                if rval:
                    vals.add(rval)
        return vals


class AnnotationDataAdapter(InviteDataAdapter, ABC):
    @abstractmethod
    def accepted(self):
        """
        The wrapped invite was accepted.
        This should be wrapped in a transaction.
        Any used invitation should clean up its data.
        """

    @classmethod
    def validate(
        cls, *, columns: list[str], rows: list[list[str | None | int]], meeting: Meeting
    ):
        """
        Perform more complex validation suitable for checks when running within a worker,
        before doing any heavy lifting.

        raise DataColValidationError if something goes wrong
        """

    @classmethod
    @abstractmethod
    def annotate(
        cls,
        *,
        invites_qs: models.QuerySet[MeetingInvite],
        columns: list[str],
        rows: list[list[str | None | int]],
        registry: InviteAdapterRegistry,
        annotations_formatted,
        meeting: Meeting,
        **kwargs,
    ):
        """
        Annotate invites if they should have other effects, for instance assigning participant numbers.
        Also take care of existing state, if users have already accepted an invitation.
        Note! This method will probably be extremely slow!

        """


class InviteUserDataAdapter(InviteDataAdapter, ABC):
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
