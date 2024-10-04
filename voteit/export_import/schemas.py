from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from itertools import chain
from typing import Any

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.text import slugify
from django.utils.timezone import now
from pydantic import BaseModel
from pydantic import Extra
from pydantic import Field
from pydantic import constr
from pydantic import validator

from voteit.agenda.models import AgendaItem
from voteit.agenda.workflows import AgendaItemWf
from voteit.discussion.models import DiscussionPost
from voteit.meeting.models import MeetingGroup
from voteit.proposal.models import DiffProposal
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument
from voteit.proposal.models import TextParagraph
from voteit.proposal.workflows import ProposalWf

User = get_user_model()

schema_context_vars = ContextVar("schema_context_vars", default=None)


def _m_to_s_default():
    return model_to_schema.copy()


class BaseContext(BaseModel, extra=Extra.forbid):
    model_to_schema: dict[type[models.Model], type[BaseModel]] = Field(
        default_factory=_m_to_s_default
    )
    clear_group_authors: bool = False  # Order matters, always before include_groups
    clear_authors: bool = False
    clear_ai_states: bool = False
    clear_proposal_states: bool = False
    clear_proposal_id: bool = False
    include_groups: bool = True
    include_proposals: bool = True
    include_discussions: bool = True

    @validator("include_groups", allow_reuse=True)
    def validate_include_groups(cls, v: bool, values: dict):
        """
        >>> _ = BaseContext()
        >>> _ = BaseContext(clear_group_authors=True)
        >>> _ = BaseContext(include_groups=False, clear_group_authors=True)
        >>> _ = BaseContext(include_groups=False)
        Traceback (most recent call last):
        ...
        pydantic.error_wrappers.ValidationError: 1 validation error for BaseContext
        include_groups
          Groups are needed to set group authors - change 'clear_group_authors' or 'include_groups'
        """
        if not v and not values.get("clear_group_authors", False):
            raise ValueError(
                "Groups are needed to set group authors - change 'clear_group_authors' or 'include_groups'"
            )
        return v


@contextmanager
def schema_context(**kwargs) -> Iterator[None]:
    """
    Override defaults when checking schema
    """

    data = BaseContext(**kwargs)
    token = schema_context_vars.set(data)
    try:
        yield
    finally:
        schema_context_vars.reset(token)


def get_context() -> BaseContext:
    if ctx := schema_context_vars.get():
        return ctx
    # defaults
    return BaseContext()


class BaseContentData(BaseModel):
    body: str = ""
    created: datetime | None
    modified: datetime | None
    # mentions:list[int] FIXME: how do we handle this?
    tags: list[constr(max_length=100, strip_whitespace=True)] = []

    class Config:
        orm_mode = True


class GroupMixin(BaseModel):
    meeting_group: (
        constr(max_length=100, strip_whitespace=True) | None
    )  # ID for meeting group
    as_group: bool = False

    @validator("meeting_group", pre=True, allow_reuse=True)
    def meeting_groupid(cls, v):
        """
        >>> grp=MeetingGroup(groupid='hi-there')
        >>> GroupMixin.meeting_groupid(grp)
        'hi-there'
        >>> with schema_context(clear_group_authors=True):
        ...     GroupMixin.meeting_groupid(grp) == None
        True
        """
        ctx = get_context()
        if ctx.clear_group_authors:
            return None
        if isinstance(v, MeetingGroup):
            return v.groupid
        return v


class UserData(BaseModel):
    email: str | None
    pk: int | None

    class Config:
        orm_mode = True
        frozen = True

    @validator("email", pre=True, allow_reuse=True)
    def transform_email(cls, v: str | None):
        if v:
            return v.strip().lower()
        return v


class AuthorMixin(BaseModel):
    author: UserData | None

    @validator("author", pre=True, allow_reuse=True)
    def author_user(cls, v):
        """
        >>> user=User(pk=111, email='john@doe.com')
        >>> AuthorMixin.author_user(user)
        UserData(email='john@doe.com', pk=111)
        >>> with schema_context(clear_authors=True):
        ...     AuthorMixin.author_user(user) == None
        True
        """
        ctx = get_context()
        if ctx.clear_authors:
            return None
        if isinstance(v, User):
            return ctx.model_to_schema[v.__class__].from_orm(v)
        return v


class TextDocumentData(BaseModel):
    title: constr(max_length=100, strip_whitespace=True)
    base_tag: constr(max_length=40, strip_whitespace=True, to_lower=True)
    body: str
    created: datetime | None
    modified: datetime | None

    class Config:
        orm_mode = True

    @validator("base_tag")
    def check_base_tag(cls, v):
        """
        >>> TextDocumentData.check_base_tag('hello-world')
        'hello-world'
        >>> TextDocumentData.check_base_tag('#Hello world!')
        Traceback (most recent call last):
        ...
        ValueError: base_tag contains chars that aren't allowed - use lowercase, numbers and -_
        """
        if v and v != slugify(v, allow_unicode=True):
            raise ValueError(
                "base_tag contains chars that aren't allowed - use lowercase, numbers and -_"
            )
        return v


class ProposalData(BaseContentData, AuthorMixin, GroupMixin):
    body: str
    state: constr(strip_whitespace=True, to_lower=True, max_length=50) | None
    prop_id: (
        constr(strip_whitespace=True, to_lower=True, max_length=50) | None
    )  # FIXME: Should we have prop_id here?

    @validator("state")
    def check_state(cls, v):
        """
        >>> ProposalData.check_state(ProposalWf.PUBLISHED)
        'published'
        >>> with schema_context(clear_proposal_states=True):
        ...     ProposalData.check_state(ProposalWf.PUBLISHED) == None
        True
        >>> _ = ProposalData.check_state(None)
        >>> ProposalData.check_state("404")
        Traceback (most recent call last):
        ...
        ValueError: 404 is not a valid proposal state
        """
        ctx = get_context()
        if ctx.clear_proposal_states:
            return
        if v and v not in ProposalWf.states:
            raise ValueError(f"{v} is not a valid proposal state")
        return v

    @validator("prop_id")
    def validate_prop_id(cls, v: str | None):
        """
        >>> ProposalData.validate_prop_id('hello-world')
        'hello-world'
        >>> with schema_context(clear_proposal_id=True):
        ...     ProposalData.validate_prop_id('hello-world') is None
        True
        >>> ProposalData.validate_prop_id('Hello world')
        Traceback (most recent call last):
        ...
        ValueError: Proposal ID contains chars that aren't allowed - use lowercase, numbers and -_
        """
        ctx = get_context()
        if ctx.clear_proposal_id:
            return
        if v and v != slugify(v, allow_unicode=True):
            raise ValueError(
                f"Proposal ID contains chars that aren't allowed. Bad value: {v}"
            )
        return v


class DiffProposalData(ProposalData):
    text_document: str = ""  # Really base tag here
    paragraph: int  # Paragraph order num, not pk!

    @validator("paragraph", pre=True, always=True, allow_reuse=True)
    def transform_paragraph(cls, v, values):
        if isinstance(v, TextParagraph):
            values["text_document"] = v.text_document.base_tag
            return v.paragraph_id
        return v


class DiscussionPostData(BaseContentData, AuthorMixin, GroupMixin):
    body: str


class MeetingGroupData(BaseContentData):
    title: constr(max_length=100, strip_whitespace=True) = ""
    groupid: constr(max_length=100, strip_whitespace=True)
    votes: int | None
    members: list[UserData] = []
    post_as: bool = False
    show_on_speaker: bool = True
    delegate_to: int | None = None

    @validator("title")
    def use_groupid_as_title_if_empty(cls, v, values: dict):
        if not v:
            v = values["groupid"]
        return v

    @validator("members", pre=True)
    def fetch_members(cls, v):
        return resolve_potential_manager(v)

    @validator("delegate_to", pre=True)
    def resolve_delegate_to(cls, v):
        """
        >>> grp=MeetingGroup(groupid='hi-there')
        >>> MeetingGroupData.resolve_delegate_to(None) is None
        True
        >>> MeetingGroupData.resolve_delegate_to(2)
        2
        >>> MeetingGroupData.resolve_delegate_to(grp)
        'hi-there'
        """
        if isinstance(v, MeetingGroup):
            return v.groupid
        return v


class AgendaItemData(BaseContentData):
    title: constr(max_length=100, strip_whitespace=True)
    state: constr(strip_whitespace=True, to_lower=True, max_length=50) | None
    block_discussion: bool = False
    block_proposals: bool = False
    text_documents: list[TextDocumentData] = []
    proposals: list[ProposalData | DiffProposalData] = []
    discussions: list[DiscussionPostData] = []

    class Config:
        orm_mode = True

    @validator("text_documents", pre=True)
    def fetch_related_text(cls, v):
        v = resolve_potential_manager(v)
        return v

    @validator("proposals", pre=True)
    def fetch_related_proposals(cls, v):
        ctx = get_context()
        if not ctx.include_proposals:
            return []
        v = resolve_potential_manager(v, select={"meeting_group", "author"})
        return v

    @validator("discussions", pre=True)
    def fetch_related_qs(cls, v):
        ctx = get_context()
        if not ctx.include_discussions:
            return []
        v = resolve_potential_manager(v, select={"meeting_group", "author"})
        return v

    @validator("proposals", pre=True)
    def select_proposal_type(cls, v: list[dict | ProposalData | DiffProposalData]):
        """
        Duck-type dict data as a proposal
        >>> f = AgendaItemData.select_proposal_type
        >>> f([{'body': 'Hello'}, {'body': 'World', 'text_document': 'hi', 'paragraph': 2}, ProposalData(body="Unchanged")])
        [ProposalData(meeting_group=None, as_group=False, author=None, body='Hello', created=None, modified=None, tags=[], state=None, prop_id=None),\
            DiffProposalData(meeting_group=None, as_group=False, author=None, body='World', created=None, modified=None, tags=[], state=None, prop_id=None, text_document='hi', paragraph=2), \
            ProposalData(meeting_group=None, as_group=False, author=None, body='Unchanged', created=None, modified=None, tags=[], state=None, prop_id=None)]
        """
        checked = []
        while v:
            item = v.pop(0)
            if isinstance(item, dict):
                if "text_document" in item:
                    item = DiffProposalData(**item)
                else:
                    item = ProposalData(**item)
            checked.append(item)
        return checked

    @validator("state")
    def check_state(cls, v):
        """
        >>> AgendaItemData.check_state(AgendaItemWf.UPCOMING)
        'upcoming'
        >>> with schema_context(clear_ai_states=True):
        ...     AgendaItemData.check_state(AgendaItemWf.UPCOMING) == None
        True
        >>> _ = AgendaItemData.check_state(None)
        >>> AgendaItemData.check_state("404")
        Traceback (most recent call last):
        ...
        ValueError: 404 is not a valid Agenda item state
        """
        ctx = get_context()
        if ctx.clear_ai_states:
            return
        if v and v not in AgendaItemWf.states:
            raise ValueError(f"{v} is not a valid Agenda item state")
        return v

    @validator("proposals")
    def unique_prop_ids(cls, v: list[ProposalData | DiffProposalData], values: dict):
        """
        >>> p = ProposalData
        >>> proposals=[p(prop_id="hi", body="Hi"), p(body="Hi")]
        >>> _ = AgendaItemData(title="Hi", proposals=proposals)
        >>> proposals=[p(prop_id="same", body="Hi"), p(prop_id="same", body="Hi")]
        >>> _ = AgendaItemData(title="Doh", proposals=proposals)
        Traceback (most recent call last):
        ...
        pydantic.error_wrappers.ValidationError: 1 validation error for AgendaItemData
        proposals
          Agenda item Doh contains proposals with duplicate proposal id: #same (type=value_error)
        """
        found = set()
        for prop in v:
            if prop.prop_id:
                if prop.prop_id in found:
                    raise ValueError(
                        f"Agenda item {values['title']} contains proposals with duplicate proposal id: #{prop.prop_id}"
                    )
                found.add(prop.prop_id)
        return v

    @validator("text_documents")
    def unique_base_tag(cls, v: list[TextDocumentData], values: dict):
        """
        >>> t = TextDocumentData
        >>> text_documents=[t(base_tag="hi", title="Hi", body="Hi"), t(base_tag="hello", title="Hi", body="Hi")]
        >>> _ = AgendaItemData(title="Hi", text_documents=text_documents)
        >>> text_documents=[t(base_tag="same", title="Hi", body="Hi"), t(base_tag="same", title="Hi", body="Hi")]
        >>> _ = AgendaItemData(title="Doh", text_documents=text_documents)
        Traceback (most recent call last):
        ...
        pydantic.error_wrappers.ValidationError: 1 validation error for AgendaItemData
        text_documents
          Agenda item Doh contains TextDocuments with duplicate base_tag: #same (type=value_error)
        """
        found = set()
        for tdd in v:
            if tdd.base_tag in found:
                raise ValueError(
                    f"Agenda item {values['title']} contains TextDocuments with duplicate base_tag: #{tdd.base_tag}"
                )
            found.add(tdd.base_tag)
        return v


# Reactions?


class MeetingStructure(BaseModel):
    groups: list[MeetingGroupData] = []
    agenda_items: list[AgendaItemData] = []

    class Config:
        orm_mode = True

    @validator("agenda_items", pre=True)
    def fetch_agenda_items(cls, v):
        return resolve_potential_manager(
            v,
            prefetch=(
                "proposals",
                "discussions",
                "text_documents",
            ),
        )

    @validator("groups", pre=True)
    def fetch_groups(cls, v):
        ctx = get_context()
        if not ctx.include_groups:
            return []
        return resolve_potential_manager(v)

    @validator("groups")
    def check_unique_groupids(cls, v: list[MeetingGroupData]):
        """
        >>> f = MeetingStructure.check_unique_groupids
        >>> d = MeetingGroupData
        >>> _ = f([d(groupid='hello'), d(groupid='world')])
        >>> f([d(groupid='same'), d(groupid='same')])
        Traceback (most recent call last):
        ...
        ValueError: Duplicate groupid(s): 'same'
        """
        used = set()
        duplicate = set()
        for mgd in v:
            if mgd.groupid in used:
                duplicate.add(mgd.groupid)
            used.add(mgd.groupid)
        if duplicate:
            raise ValueError("Duplicate groupid(s): '%s'" % "', '".join(duplicate))
        return v

    @validator("agenda_items")
    def check_groupids(cls, v: list[AgendaItemData], values):
        """
        >>> groups = [MeetingGroupData(groupid='hi')]
        >>> proposals = [ProposalData(meeting_group=None, body="Hi"), ProposalData(meeting_group='hi', body="Hi")]
        >>> discussions = [DiscussionPostData(meeting_group=None, body="Hi"),DiscussionPostData(meeting_group='hi', body="Hi")]
        >>> agenda_items= [AgendaItemData(title='Item 1', proposals=proposals, discussions=discussions)]
        >>> _ = MeetingStructure(groups=groups, agenda_items=agenda_items)
        >>> proposals = [ProposalData(meeting_group='404', body="Hi"), ProposalData(meeting_group='hi', body="Hi")]
        >>> agenda_items= [AgendaItemData(title='Item 1', proposals=proposals, discussions=discussions)]
        >>> _ = MeetingStructure(groups=groups, agenda_items=agenda_items)
        Traceback (most recent call last):
        ...
        pydantic.error_wrappers.ValidationError: 1 validation error for MeetingStructure
        """
        groupids = {mgd.groupid for mgd in values.get("groups", [])}
        for aid in v:
            for obj in chain(aid.proposals, aid.discussions):
                if obj.meeting_group and obj.meeting_group not in groupids:
                    raise ValueError(
                        "%s is not a valid meeting group id" % obj.meeting_group
                    )
        return v


def resolve_potential_manager(v: models.Manager | Any, prefetch=(), select=()):
    if isinstance(v, models.Manager):
        if hasattr(v, "select_subclasses"):
            v = v.select_subclasses()
        if prefetch:
            v = v.prefetch_related(*prefetch)
        if select:
            v = v.select_related(*select)
        ctx = get_context()
        return [ctx.model_to_schema[o.__class__].from_orm(o) for o in v.all()]
    return v


model_to_schema = {
    AgendaItem: AgendaItemData,
    MeetingGroup: MeetingGroupData,
    TextDocument: TextDocumentData,
    Proposal: ProposalData,
    DiffProposal: DiffProposalData,
    DiscussionPost: DiscussionPostData,
    User: UserData,
}


class ImportStats(BaseModel):
    agenda_items: int = 0
    groups: int = 0
    proposals: int = 0
    diff_proposals: int = 0
    discussion_posts: int = 0
    text_documents: int = 0


class ImportMeetingMeta(BaseModel):
    version: int
    created: datetime | None
    title: str = ""
    description: str = ""


class ImportMeetingStructure(MeetingStructure):
    meta: ImportMeetingMeta | None


class ExportMeetingMeta(BaseModel):
    version: int = 1
    created: datetime = now()
    title: str = ""
    description: str = ""


class ExportMeetingStructure(MeetingStructure):
    meta: ExportMeetingMeta = Field(default_factory=ExportMeetingMeta)
