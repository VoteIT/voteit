from __future__ import annotations
from contextlib import suppress
from typing import TYPE_CHECKING
from typing import TypeVar

from pydantic.main import BaseModel
from django.db import models
from typing import Generator

from voteit.core.component import Registry
from voteit.core.decorators import ensure_atomic
from voteit.invites.abcs import AnnotationDataAdapter
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
            candidate_keys = set(factory.schema.schema()["properties"].keys())
            for v in self.values():
                if not issubclass(v, InviteUserDataAdapter):
                    continue
                clash = candidate_keys.intersection(
                    v.schema.schema()["properties"].keys()
                )
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
                raise ValueError(f"{k} is not a valid column")
            if columns.count(k) > 1:
                raise ValueError(f"Duplicate columns. Found several {k}")

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
                        f"The value {k}={v} is used within different subsets of user data. Offending row: {i}"
                    )
            checked.append(items)

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
            l = len(row)
            yield {columns[i]: row[i] for i in idx if i < l and row[i]}

    def format_for_annotations(
        self, columns: list[str], rows: list[list[str | None | int]]
    ):
        """
        >>> from voteit.invites.app.invites.email import InviteEmail
        >>> from voteit.invites.app.invites.group import InviteGroup
        >>> from voteit.invites.abcs import InviteDataAdapter
        >>> testing_reg = InviteAdapterRegistry(InviteDataAdapter)
        >>> _ = testing_reg(InviteEmail)
        >>> _ = testing_reg(InviteGroup)
        >>> out = testing_reg.format_for_annotations(['email', 'group'], [['jeff@betahaus.net', '123'], ['jane@betahaus.net', '123']])
        >>> list(out)
        [(dict_items([('email', 'jeff@betahaus.net')]), {'email': 'jeff@betahaus.net', 'group': '123'}), (dict_items([('email', 'jane@betahaus.net')]), {'email': 'jane@betahaus.net', 'group': '123'})]
        """
        for row in rows:
            yield {
                columns[i]: x
                for i, x in enumerate(row)
                if columns[i] in self.user_data_keys
            }.items(), {columns[i]: x for i, x in enumerate(row)}

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
        annotations_formatted = list(self.format_for_annotations(columns, rows))
        for adapter in self.get_annotations(columns):
            # Yield results, display progress etc?
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


invite_adapter_registry = InviteAdapterRegistry(InviteDataAdapter)
