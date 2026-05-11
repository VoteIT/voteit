from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING
from django.utils.translation import gettext_lazy as _
from django.utils.functional import classproperty
from pydantic import BaseModel
from django.db import models
from typing import Generator

from voteit.invites.exceptions import DataColValidationError


if TYPE_CHECKING:
    from voteit.invites.models import MeetingInvite
    from voteit.meeting.models import Meeting
    from voteit.invites.registries import InviteAdapterRegistry
    from voteit.invites.schemas import AnnotationResultSchema


@dataclass(frozen=True)
class FormattedAnnotationRow:
    """A CSV row split into identity data (for invite matching) and full row data (for effect application)."""

    user_data: dict  # identity columns only (email, ssn) — used to match against invite.user_data
    row_data: dict  # all columns including effect columns (group, grouprole)


class InviteDataAdapter(ABC):
    # This is information to frontend that clear can be run
    is_clearable: bool = False
    # Some adapters are just markers that don't process the data themselves
    is_runnable: bool = True

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
    def schema(self) -> type[BaseModel]: ...

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
                    except ValueError:
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
        annotations_formatted: list[FormattedAnnotationRow],
        meeting: Meeting,
        **kwargs,
    ) -> AnnotationResultSchema | None:
        """
        Annotate invites if they should have other effects, for instance assigning participant numbers.
        Also take care of existing state, if users have already accepted an invitation.
        Note! This method will probably be extremely slow!
        """

    @classproperty
    def invite_qs_annotation_name(cls):
        return f"has_{cls.name}_ann"

    @classmethod
    def prep_invites_qs_for_subscribe(
        cls, invites_qs: models.QuerySet[MeetingInvite]
    ) -> models.QuerySet[MeetingInvite]:
        """
        Attach information about annotations on the queryset itself in advance of serialization.
        Information should be passed along to method 'has_annotations' and doesn't need to result
        in anything else than a bool value.
        Must return updated queryset!
        """
        return invites_qs

    def has_annotations(self, from_qs: bool = True) -> bool | None:
        """
        Does this method have any annotations?
        """
        if from_qs:
            return getattr(self.invite, self.invite_qs_annotation_name, None)
        else:
            for val in self.get_annotations():
                if val:
                    return True
            return False

    def get_annotations(self) -> Generator[dict]:
        """
        Return any present annotations for a specific invite.
        It should be in the format of a json-ready dict.
        """
        yield from []

    @classmethod
    @abstractmethod
    def clear(cls, meeting: Meeting) -> models.QuerySet[MeetingInvite]:
        """
        Clear annotations of this kind. Return invites that were affected by the clear operation.
        """


class InviteUserDataAdapter(InviteDataAdapter, ABC):
    @classmethod
    def query(cls, *values) -> models.Q:
        return models.Q(**{f"user_data__{cls.name}__in": values})

    @staticmethod
    def mask(v: str) -> str:
        """
        Override method to implement masking
        """
        return v
