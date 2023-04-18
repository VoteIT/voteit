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


class InviteDataAdapter(ABC):
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
                if row[i]:
                    try:
                        data = cls.schema(**{cls.name: row[i]})
                    except ValueError as exc:
                        bad_rows.append(num)
                        continue
                    row[i] = getattr(data, cls.name)
            if bad_rows:
                raise DataColValidationError(name=cls.name, index=i + 1, rows=bad_rows)


class InviteUserDataAdapter(InviteDataAdapter, ABC):
    @classmethod
    def schema_keys(cls) -> set[str]:
        return set(cls.schema.schema()["properties"].keys())

    @classmethod
    def query(cls, *values) -> models.Q:
        return models.Q(**{f"user_data__{cls.name}__in": values})

    # @classmethod
    # def from_cols(cls, *cols: str) -> BaseModel:
    #     if len(cols) != len(cls.columns):
    #         raise ValueError(
    #             f"Must have exactly {len(cls.columns)} positional arguments"
    #         )
    #     return cls.schema(**dict(zip(cls.columns, cols)))


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
