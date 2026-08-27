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


def get_cell(row: list, i: int):
    """
    Fetch a cell from a row, normalising anything empty to None.

    Rows may be shorter or longer than the column list, and empty values vary in
    type -- see RowColInvitesBaseSchema.check_important_data_outside_read_columns.

    >>> get_cell(['a', '', '  ', None, 0], 0)
    'a'
    >>> get_cell(['a', '', '  ', None, 0], 1) is None
    True
    >>> get_cell(['a', '', '  ', None, 0], 2) is None
    True
    >>> get_cell(['a', '', '  ', None, 0], 3) is None
    True
    >>> get_cell(['a', '', '  ', None, 0], 4) is None
    True
    >>> get_cell(['a'], 10) is None
    True
    """
    try:
        val = row[i]
    except IndexError:
        return None
    if isinstance(val, str):
        val = val.strip()
    return val or None


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
    # Columns that, together with the row's identity data, identify the single
    # record this adapter writes. Rows sharing that key collapse into one write.
    collapse_key_columns: tuple[str, ...] = ()
    # Columns whose value must not differ between rows sharing a collapse key --
    # a later row silently winning is a data error, not an update.
    # Empty disables the check.
    no_overwrite_columns: tuple[str, ...] = ()

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
    def check_conflicting_rows(
        cls,
        *,
        columns: list[str],
        rows: list[list[str | None | int]],
        registry: InviteAdapterRegistry,
    ):
        """
        Reject rows that collapse into the same write but disagree about its content.

        Several rows may describe the same recipient -- one per group, say -- and
        several of them may collapse into a single record. Repeating a row verbatim
        is harmless, but when two such rows differ the later one silently wins and
        the earlier one is thrown away without a word. Adapters opt in by declaring
        ``collapse_key_columns`` and ``no_overwrite_columns``.

        Rows are numbered from 1, like everywhere else in this pipeline. Run this
        after preflight, so values have been normalised and 'Main' doesn't look
        different from 'main'.

        >>> from voteit.invites.app.invites.email import InviteEmail
        >>> from voteit.invites.app.invites.group import InviteGroup
        >>> from voteit.invites.registries import InviteAdapterRegistry
        >>> testing_reg = InviteAdapterRegistry(InviteDataAdapter)
        >>> _ = testing_reg(InviteEmail)
        >>> _ = testing_reg(InviteGroup)
        >>> columns = ['email', 'group', 'grouprole']

        A repeated row is fine, and so is the same person in two groups:

        >>> InviteGroup.check_conflicting_rows(
        ...     columns=columns,
        ...     rows=[['a@x.com', 'board', 'main'], ['a@x.com', 'board', 'main']],
        ...     registry=testing_reg,
        ... )
        >>> InviteGroup.check_conflicting_rows(
        ...     columns=columns,
        ...     rows=[['a@x.com', 'board', 'main'], ['a@x.com', 'staff', 'subst']],
        ...     registry=testing_reg,
        ... )

        Two roles for the same person and group are not:

        >>> InviteGroup.check_conflicting_rows(
        ...     columns=columns,
        ...     rows=[['a@x.com', 'board', 'main'], ['a@x.com', 'board', 'subst']],
        ...     registry=testing_reg,
        ... )
        Traceback (most recent call last):
        ...
        voteit.invites.exceptions.DataColValidationError: Rows 1 and 2 set
        different 'grouprole' for the same email=a@x.com, group=board:
        'main' vs 'subst'. The later row would silently overwrite the earlier
        one - remove one of them or make the rows agree.

        Leaving the column blank on one of them counts as a difference, since the
        role would be dropped:

        >>> InviteGroup.check_conflicting_rows(
        ...     columns=columns,
        ...     rows=[['a@x.com', 'board', 'main'], ['a@x.com', 'board', '']],
        ...     registry=testing_reg,
        ... )
        Traceback (most recent call last):
        ...
        voteit.invites.exceptions.DataColValidationError: Rows 1 and 2 set different ...
        """
        # Duplicate columns are rejected by registry.check_column_req before we get
        # here, so a column name maps to exactly one index.
        value_cols = [
            (c, columns.index(c)) for c in cls.no_overwrite_columns if c in columns
        ]
        if not value_cols:
            return
        key_cols = [
            (c, columns.index(c)) for c in cls.collapse_key_columns if c in columns
        ]
        seen: dict[tuple, tuple[int, tuple]] = {}
        ud_seq = registry.build_ud_query_seq(columns, rows)
        for num, (ud, row) in enumerate(zip(ud_seq, rows), 1):
            if not ud:
                continue
            key_values = tuple(get_cell(row, i) for _c, i in key_cols)
            if any(v is None for v in key_values):
                # Nothing is written for this row
                continue
            key = (frozenset(ud.items()), key_values)
            values = tuple(get_cell(row, i) for _c, i in value_cols)
            first_num, first_values = seen.setdefault(key, (num, values))
            if first_values == values:
                continue
            (col_name, col_idx), old_val, new_val = next(
                (col, old, new)
                for col, old, new in zip(value_cols, first_values, values)
                if old != new
            )
            described = ", ".join(
                f"{k}={v}"
                for k, v in sorted(ud.items())
                + [(c, v) for (c, _i), v in zip(key_cols, key_values)]
            )
            raise DataColValidationError(
                name=col_name,
                index=col_idx + 1,
                rows=[first_num, num],
                message=_(
                    "Rows %(first_row)s and %(row_no)s set different '%(column)s' "
                    "for the same %(described)s: %(old)s vs %(new)s. The later row "
                    "would silently overwrite the earlier one - remove one of them "
                    "or make the rows agree."
                )
                % {
                    "first_row": first_num,
                    "row_no": num,
                    "column": col_name,
                    "described": described,
                    "old": repr(old_val),
                    "new": repr(new_val),
                },
            )

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

    @classmethod
    def clear_for_invites(cls, invite_pks: list[int]) -> int:
        """
        Clear annotations of this kind for a specific set of invites.
        Returns the number of annotation records deleted.
        Clearable adapters should override this; the default does nothing.
        """
        return 0


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
