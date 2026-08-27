from __future__ import annotations
from contextlib import suppress
from typing import TYPE_CHECKING
from typing import TypeVar

from django.db import models
from django.utils.translation import gettext_lazy as _
from typing import Generator

from voteit.core.component import Registry
from voteit.core.decorators import ensure_atomic
from voteit.invites.abcs import AnnotationDataAdapter
from voteit.invites.abcs import FormattedAnnotationRow
from voteit.invites.abcs import InviteDataAdapter
from voteit.invites.abcs import InviteUserDataAdapter

if TYPE_CHECKING:
    from voteit.invites.models import MeetingInvite
    from voteit.invites.schemas import AnnotationResultSchema
    from voteit.meeting.models import Meeting

T = TypeVar("T")


class InviteAdapterRegistry(Registry[AnnotationDataAdapter, InviteUserDataAdapter]):
    def get_user_data_idx(self, columns: list[str]):
        colidx = []
        for i, colname in enumerate(columns):
            if colname in self.user_data_keys:
                colidx.append(i)
        return colidx

    def __setitem__(
        self, key: str, factory: type[InviteUserDataAdapter | AnnotationDataAdapter]
    ):
        """
        >>> from pydantic.main import BaseModel
        >>> testing_reg = InviteAdapterRegistry(InviteDataAdapter)

        >>> class HelloSchema(BaseModel):
        ...     world:int|None
        ...
        >>> @testing_reg
        ... class Hello(InviteUserDataAdapter):
        ...     schema=HelloSchema
        ...     name='hello'

        >>> testing_reg['oh_no'] = Hello
        Traceback (most recent call last):
        ...
        ValueError: If you register <class 'voteit.invites.registries.Hello'> it will clash \
        with existing <class 'voteit.invites.registries.Hello'>. Schema attributes {'world'} are the same
        """
        if issubclass(factory, InviteUserDataAdapter):
            candidate_keys = set(factory.schema.model_fields)
            for v in self.values():
                if not issubclass(v, InviteUserDataAdapter):
                    continue
                clash = candidate_keys.intersection(v.schema.model_fields)
                if clash:
                    raise ValueError(
                        f"If you register {factory} it will clash with existing {v}, schema attributes {clash} are the same"
                    )
            if hasattr(self, "_user_data_keys"):
                delattr(self, "_user_data_keys")
        super().__setitem__(key, factory)

    def __delitem__(self, key: str):
        if hasattr(self, "_user_data_keys"):
            delattr(self, "_user_data_keys")
        super().__delitem__(key)

    @property
    def user_data_keys(self) -> set[str]:
        """
        Cached user_data_keys
        >>> from voteit.invites.app.invites.email import InviteEmail
        >>> from voteit.invites.app.invites.group import InviteGroup
        >>> from voteit.invites.app.invites.grouprole import InviteGroupRole
        >>> from voteit.invites.abcs import InviteDataAdapter
        >>> testing_reg = InviteAdapterRegistry(InviteDataAdapter)
        >>> testing_reg.user_data_keys
        set()
        >>> _ = testing_reg(InviteGroup)
        >>> testing_reg.user_data_keys
        set()
        >>> _ = testing_reg(InviteEmail)
        >>> testing_reg.user_data_keys
        {'email'}
        >>> del testing_reg[InviteEmail.name]
        >>> testing_reg.user_data_keys
        set()
        """
        with suppress(AttributeError):
            return self._user_data_keys
        keys = set()
        for v in self.values():
            if issubclass(v, InviteUserDataAdapter):
                keys.add(v.name)
        self._user_data_keys = keys
        return keys

    @property
    def annotation_adapters(self) -> Generator[type[AnnotationDataAdapter]]:
        for v in self.values():
            if v.is_annotation:
                yield v

    def check_column_req(self, columns: list[str]):
        """
        >>> from voteit.invites.app.invites.email import InviteEmail
        >>> from voteit.invites.app.invites.group import InviteGroup
        >>> from voteit.invites.app.invites.grouprole import InviteGroupRole
        >>> from voteit.invites.abcs import InviteDataAdapter
        >>> testing_reg = InviteAdapterRegistry(InviteDataAdapter)
        >>> _ = testing_reg(InviteGroup)
        >>> _ = testing_reg(InviteGroupRole)
        >>> _ = testing_reg(InviteEmail)
        >>> testing_reg.check_column_req(['group'])
        >>> testing_reg.check_column_req(['group', 'grouprole'])
        >>> testing_reg.check_column_req(['booo'])
        Traceback (most recent call last):
        ...
        ValueError: booo is not a valid column
        >>> testing_reg.check_column_req(['grouprole'])
        Traceback (most recent call last):
        ...
        ValueError: GroupRole requires the column left of it to be group
        >>> testing_reg.check_column_req(['email'])
        >>> testing_reg.check_column_req(['email', 'email'])
        Traceback (most recent call last):
        ...
        ValueError: User data can't have duplicate columns. Found several email
        """
        for k in columns:
            try:
                self[k].check_column_req(columns)
            except KeyError:
                raise ValueError(_("%(column)s is not a valid column") % {"column": k})
            if columns.count(k) > 1:
                raise ValueError(
                    _("Duplicate columns. Found several %(column)s") % {"column": k}
                )

    def preflight(self, columns: list[str], rows: list[list[str]]) -> None:
        """
        Execute preflight for all relevant columns. It only needs to run once.
        """
        for k in set(columns):
            self[k].preflight(columns, rows)

    def check_intersections(self, columns: list[str], rows: list[list[str]]) -> None:
        """
        Make sure no intersections exist within the data.
        """
        cmpvals = []
        checked = []
        queryseq = list(self.build_ud_query_seq(columns, rows))
        for ud in queryseq:
            items = ud.items()
            if items not in cmpvals:
                cmpvals.append(items)
        for i, ud in enumerate(queryseq, 1):
            items = ud.items()
            if items in checked:  # Exact match ok
                continue
            for k, v in items:
                di = {k: v}.items()
                if any(di <= x for x in cmpvals if items != x):
                    raise ValueError(
                        _(
                            "The value %(key)s=%(value)s is used within different "
                            "subsets of user data. Offending row: %(row_no)s"
                        )
                        % {"key": k, "value": v, "row_no": i}
                    )
            checked.append(items)

    def check_conflicting_roles(
        self,
        columns: list[str],
        rows: list[list[str]],
        roles_per_row: list[list[str]],
    ) -> None:
        """
        The same recipient may appear on several rows -- one row per group, say --
        but those rows must agree on roles. Rows are grouped by role combination
        before invites are written, so conflicting roles would simply mean that
        the last combination processed wins, silently discarding the others.

        ``roles_per_row`` must be parallel to ``rows``, as returned by
        ``extract_roles_per_row``.

        >>> from voteit.invites.app.invites.email import InviteEmail
        >>> from voteit.invites.app.invites.group import InviteGroup
        >>> from voteit.invites.abcs import InviteDataAdapter
        >>> testing_reg = InviteAdapterRegistry(InviteDataAdapter)
        >>> _ = testing_reg(InviteEmail)
        >>> _ = testing_reg(InviteGroup)
        >>> columns = ['email', 'group']
        >>> rows = [['a@x.com', 'board'], ['a@x.com', 'staff']]

        Same recipient in two groups with the same roles is fine:

        >>> testing_reg.check_conflicting_roles(columns, rows, [['pa'], ['pa']])

        Differing roles are not:

        >>> testing_reg.check_conflicting_roles(columns, rows, [['mo', 'pa'], ['pa']])
        Traceback (most recent call last):
        ...
        ValueError: The same user data has different roles on rows 1 and 2: email=a@x.com
        """
        seen: dict[frozenset, tuple[int, list[str]]] = {}
        for i, ud in enumerate(self.build_ud_query_seq(columns, rows), 1):
            if not ud:
                continue
            roles = roles_per_row[i - 1]
            first_row, first_roles = seen.setdefault(frozenset(ud.items()), (i, roles))
            if list(first_roles) != list(roles):
                values = ", ".join(f"{k}={v}" for k, v in sorted(ud.items()))
                raise ValueError(
                    _(
                        "The same user data has different roles on rows "
                        "%(first_row)s and %(row_no)s: %(values)s"
                    )
                    % {"first_row": first_row, "row_no": i, "values": values}
                )

    def check_conflicting_annotations(
        self, columns: list[str], rows: list[list[str]]
    ) -> None:
        """
        Let every annotation adapter reject rows that would silently overwrite
        each other. See AnnotationDataAdapter.check_conflicting_rows.

        Must run after preflight, so values are already normalised.

        >>> from voteit.invites.app.invites.email import InviteEmail
        >>> from voteit.invites.app.invites.group import InviteGroup
        >>> from voteit.invites.app.invites.grouprole import InviteGroupRole
        >>> from voteit.invites.abcs import InviteDataAdapter
        >>> testing_reg = InviteAdapterRegistry(InviteDataAdapter)
        >>> _ = testing_reg(InviteEmail)
        >>> _ = testing_reg(InviteGroup)
        >>> _ = testing_reg(InviteGroupRole)
        >>> columns = ['email', 'group', 'grouprole']

        >>> testing_reg.check_conflicting_annotations(
        ...     columns, [['a@x.com', 'board', 'main'], ['a@x.com', 'board', 'main']]
        ... )
        >>> testing_reg.check_conflicting_annotations(
        ...     columns, [['a@x.com', 'board', 'main'], ['a@x.com', 'board', 'subst']]
        ... )
        Traceback (most recent call last):
        ...
        voteit.invites.exceptions.DataColValidationError: Rows 1 and 2 set
        different 'grouprole' ...

        Adapters that declare no columns to protect are simply skipped:

        >>> testing_reg.check_conflicting_annotations(
        ...     ['email', 'group'], [['a@x.com', 'board'], ['a@x.com', 'staff']]
        ... )
        """
        for adapter in self.get_annotations(columns):
            adapter.check_conflicting_rows(columns=columns, rows=rows, registry=self)

    def build_ud_query_seq(
        self, columns: list[str], rows: list[list[str]]
    ) -> Generator[dict[str, str]]:
        """
        >>> from voteit.invites.app.invites.email import InviteEmail
        >>> from voteit.invites.app.invites.swedish_ssn import InviteSweSSN
        >>> from voteit.invites.app.invites.group import InviteGroup
        >>> from voteit.invites.abcs import InviteDataAdapter
        >>> testing_reg = InviteAdapterRegistry(InviteDataAdapter)
        >>> _ = testing_reg(InviteEmail)
        >>> _ = testing_reg(InviteGroup)
        >>> _ = testing_reg(InviteSweSSN)
        >>> out = testing_reg.build_ud_query_seq(['email', 'group'], [['jeff@betahaus.net', '123'], ['jane@betahaus.net', '123']])
        >>> list(out)
        [{'email': 'jeff@betahaus.net'}, {'email': 'jane@betahaus.net'}]

        Falsy vals excluded
        >>> out = testing_reg.build_ud_query_seq(['email', 'swedish_ssn'], [['jeff@betahaus.net', None], [None, '123']])
        >>> list(out)
        [{'email': 'jeff@betahaus.net'}, {'swedish_ssn': '123'}]
        """
        idx = self.get_user_data_idx(columns)
        for row in rows:
            length = len(row)
            yield {columns[i]: row[i] for i in idx if i < length and row[i]}

    def format_effect_rows(
        self, columns: list[str], rows: list[list[str | None | int]]
    ) -> Generator[FormattedAnnotationRow]:
        """
        Split each CSV row into identity data (for invite matching) and full row data (for effect application).

        >>> from voteit.invites.app.invites.email import InviteEmail
        >>> from voteit.invites.app.invites.group import InviteGroup
        >>> from voteit.invites.abcs import InviteDataAdapter
        >>> testing_reg = InviteAdapterRegistry(InviteDataAdapter)
        >>> _ = testing_reg(InviteEmail)
        >>> _ = testing_reg(InviteGroup)
        >>> out = testing_reg.format_effect_rows(['email', 'group'], [['jeff@betahaus.net', '123'], ['jane@betahaus.net', '123']])
        >>> list(out)
        [FormattedAnnotationRow(user_data={'email': 'jeff@betahaus.net'}, row_data={'email': 'jeff@betahaus.net', 'group': '123'}), FormattedAnnotationRow(user_data={'email': 'jane@betahaus.net'}, row_data={'email': 'jane@betahaus.net', 'group': '123'})]
        """
        for row in rows:
            row = row[: len(columns)]
            yield FormattedAnnotationRow(
                user_data={
                    columns[i]: x
                    for i, x in enumerate(row)
                    if columns[i] in self.user_data_keys
                },
                row_data={columns[i]: x for i, x in enumerate(row)},
            )

    def format_for_annotations(
        self, columns: list[str], rows: list[list[str | None | int]]
    ):
        """Deprecated: use format_effect_rows() instead."""
        for r in self.format_effect_rows(columns, rows):
            yield r.user_data.items(), r.row_data

    def get_annotations(self, columns: list[str]) -> list[type[AnnotationDataAdapter]]:
        result = []
        for k in columns:
            v = self[k]
            if v.is_annotation and k not in result:
                result.append(v)
        return result

    def run_validators(
        self, columns: list[str], rows: list[list[str]], *, meeting: Meeting
    ):
        for adapter in self.get_annotations(columns):
            adapter.validate(columns=columns, rows=rows, meeting=meeting)

    @ensure_atomic
    def run_annotations(
        self,
        *,
        columns: list[str],
        rows: list[list[str]],
        invites_qs: models.QuerySet[MeetingInvite],
        meeting: Meeting,
    ) -> Generator[AnnotationResultSchema, None]:
        annotations_formatted = list(self.format_effect_rows(columns, rows))
        for adapter in self.get_annotations(columns):
            yield adapter.annotate(
                columns=columns,
                rows=rows,
                invites_qs=invites_qs,
                registry=self,
                meeting=meeting,
                annotations_formatted=annotations_formatted,
            )

    def run_accepted(self, invite: MeetingInvite):
        for adapter in self.values():
            adapter: type[AnnotationDataAdapter]
            if adapter.is_annotation:
                adapted = adapter(invite)
                adapted.accepted()

    def prep_invites_qs_for_subscribe(
        self, invites_qs: models.QuerySet[MeetingInvite]
    ) -> models.QuerySet[MeetingInvite]:
        for adapter in self.annotation_adapters:
            invites_qs = adapter.prep_invites_qs_for_subscribe(invites_qs)
        return invites_qs

    def has_annotations(self, invite: MeetingInvite, from_qs: bool = True) -> bool:
        for adapter in self.annotation_adapters:
            adapted = adapter(invite)
            if adapted.has_annotations(from_qs=from_qs):
                return True
        return False

    @ensure_atomic
    def clear(self, meeting: Meeting, *names) -> models.QuerySet[MeetingInvite]:
        invites_qs = meeting.invites.none()
        for k in names:
            invites_qs |= self[k].clear(meeting)
        return invites_qs.distinct()

    @ensure_atomic
    def clear_for_invites(self, invite_pks: list[int]) -> int:
        return sum(
            adapter.clear_for_invites(invite_pks)
            for adapter in self.values()
            if adapter.is_clearable
        )

    def get_masked_user_data(self, values: dict) -> dict:
        return {
            k: self[k].mask(v) for k, v in values.items() if k in self.user_data_keys
        }


invite_adapter_registry = InviteAdapterRegistry(InviteDataAdapter)
