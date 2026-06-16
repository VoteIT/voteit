from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from itertools import chain
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.text import slugify
from django.utils.timezone import now
from pydantic import BaseModel
from pydantic import Extra
from pydantic import Field
from pydantic import constr
from pydantic import root_validator
from pydantic import validator

from voteit.core.utils import strict_clean_html
from voteit.core.utils import strip_html
from voteit.agenda.models import AgendaItem
from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.discussion.models import DiscussionPost
from voteit.meeting.models import MeetingGroup
from voteit.notes.models import Note
from voteit.proposal.models import DiffProposal
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument
from voteit.proposal.models import TextParagraph
from voteit.proposal.statemachines import ProposalStateMachine
from voteit.reactions.models import Reaction
from voteit.reactions.models import ReactionButton

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
    include_buttons: bool = True
    include_reactions: bool = False
    include_notes: bool = False  # This should be restrictive, not via rest API!

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

    @validator("include_reactions", allow_reuse=True)
    def validate_include_reactions(cls, v: bool, values: dict):
        """
        >>> _ = BaseContext()
        >>> _ = BaseContext(include_reactions=True)
        >>> _ = BaseContext(include_reactions=False)
        >>> _ = BaseContext(include_buttons=False, include_reactions=True)
        Traceback (most recent call last):
        ...
        pydantic.error_wrappers.ValidationError: 1 validation error for BaseContext
        include_reactions
          Buttons are needed to set reactions - change 'include_buttons'
        """
        if v and not values.get("include_buttons", False):
            raise ValueError(
                "Buttons are needed to set reactions - change 'include_buttons'"
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
    pk: str | None

    class Config:
        orm_mode = True

    @validator("pk", pre=True)
    def convert_pk(cls, v):
        """
        Change to an unusable form to avoid mistakes later on.
        """
        if isinstance(v, int):
            v = str(v)
        if isinstance(v, str) and not v.startswith("_"):
            v = "_" + v
        return v


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


class AuthorMixin(BaseModel):
    author: str | None

    @validator("author", pre=True, allow_reuse=True)
    def author_user(cls, v):
        """
        >>> user=User(pk=111, email='john@doe.com', username="john")
        >>> AuthorMixin.author_user(user)
        'john'
        >>> with schema_context(clear_authors=True):
        ...     AuthorMixin.author_user(user) == None
        True
        """
        ctx = get_context()
        if ctx.clear_authors:
            return None
        if isinstance(v, User):
            return v.username
        return v


class TextDocumentData(BaseModel):
    title: constr(max_length=100, strip_whitespace=True)
    base_tag: constr(max_length=40, strip_whitespace=True, to_lower=True)
    body: str
    created: datetime | None
    modified: datetime | None

    class Config:
        orm_mode = True

    @validator("title", "body", pre=True, allow_reuse=True)
    def strip_html_from_text_doc(cls, v):
        return strip_html(v) if isinstance(v, str) else v

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

    @validator("body", pre=True, allow_reuse=True)
    def clean_proposal_body(cls, v):
        return strict_clean_html(v) if isinstance(v, str) else v

    @validator("state")
    def check_state(cls, v):
        """
        >>> ProposalData.check_state("published")
        'published'
        >>> with schema_context(clear_proposal_states=True):
        ...     ProposalData.check_state("published") == None
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
        if v and v not in {s.value for s in ProposalStateMachine.states}:
            raise ValueError(f"{v} is not a valid proposal state")
        return v

    @root_validator(pre=True)  # Before validate_prop_id
    def maybe_clear_prop_id_from_tags(cls, values):
        """
        >>> ProposalData(prop_id='hello', tags=['hello','world'], body="").dict(include={'tags'})
        {'tags': ['hello', 'world']}
        >>> with schema_context(clear_proposal_id=True):
        ...     ProposalData(prop_id='hello', tags=['hello','world'], body="").dict(include={'tags'})
        {'tags': ['world']}
        """
        ctx = get_context()
        if ctx.clear_proposal_id:
            if tags := values.get("tags"):
                if prop_id := values.get("prop_id"):
                    if prop_id in tags:
                        tags.remove(prop_id)
        return values

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

    @validator("body", pre=True, allow_reuse=True)
    def clean_discussion_body(cls, v):
        return strict_clean_html(v) if isinstance(v, str) else v


class ReactionData(BaseModel):
    username: str
    agenda_item_id: str
    content_type: list[str]
    object_id: str

    class Config:
        orm_mode = True

    @validator("content_type", pre=True)
    def ct_to_natural_key(cls, v):
        if not isinstance(v, list):
            # Consistent behaviour + json friendly
            # We always point to base object. Mistake or not, but that's what we've been doing...
            nat_key = list(v.natural_key())
            if nat_key[1] == "diffproposal":
                nat_key[1] = "proposal"
            return nat_key
        if len(v) != 2:
            raise ValueError("Not a list with 2 items")
        return v

    @validator("object_id", "agenda_item_id", pre=True)
    def convert_ids(cls, v):
        """
        Change to an unusable form to avoid mistakes later on.
        """
        if isinstance(v, int):
            v = str(v)
        if isinstance(v, str) and not v.startswith("_"):
            v = "_" + v
        return v


class ReactionButtonData(BaseModel):
    title: constr(max_length=80, strip_whitespace=True) = ""
    description: constr(max_length=100, strip_whitespace=True) = ""
    icon: constr(max_length=30, strip_whitespace=True) = ""
    color: constr(max_length=15, strip_whitespace=True)
    target: int | None
    order: int = 0
    change_roles: list[str]
    list_roles: list[str]
    active: bool = True
    allowed_models: list[str] = []
    on_presentation: bool = False
    on_vote: bool = False
    vote_template: bool = False
    flag_mode: bool = False
    reactions: list[ReactionData] = []

    class Config:
        orm_mode = True

    @validator("title", "description", "icon", "color", pre=True, allow_reuse=True)
    def strip_html_from_button_fields(cls, v):
        return strip_html(v) if isinstance(v, str) else v

    @validator("reactions", pre=True)
    def resolve_reactions(cls, v):
        ctx = get_context()
        if ctx.include_reactions:
            if isinstance(v, (models.QuerySet, models.Manager)):
                v = v.annotate(username=models.F("user__username"))
                if not ctx.include_discussions:
                    v = v.exclude(
                        content_type=ContentType.objects.get_for_model(DiscussionPost)
                    )
                if not ctx.include_proposals:
                    v = v.exclude(
                        content_type__in=ContentType.objects.get_for_models(
                            Proposal, DiffProposal
                        ).values()
                    )
            else:
                # Not a manager
                allowed_type = set()
                if ctx.include_proposals:
                    allowed_type.add("proposal")
                if ctx.include_discussions:
                    allowed_type.add("discussion")
                v = [x for x in v if x["content_type"][0] in allowed_type]
            return resolve_potential_manager(v)
        return []


class NoteData(BaseModel):
    user: str
    proposal_id: str
    body: str = ""
    intent: str = ""
    created: datetime | None

    class Config:
        orm_mode = True

    @validator("body", pre=True, allow_reuse=True)
    def clean_note_body(cls, v):
        return strict_clean_html(v) if isinstance(v, str) else v

    @validator("intent", pre=True, allow_reuse=True)
    def strip_html_from_intent(cls, v):
        return strip_html(v) if isinstance(v, str) else v

    @validator("proposal_id", pre=True)
    def convert_ids(cls, v):
        """
        Change to an unusable form to avoid mistakes later on.
        """
        if isinstance(v, int):
            v = str(v)
        if isinstance(v, str) and not v.startswith("_"):
            v = "_" + v
        return v

    @validator("user", pre=True)
    def to_username(cls, v):
        if isinstance(v, User):
            return v.username
        return v


class MeetingGroupData(BaseContentData):
    title: constr(max_length=100, strip_whitespace=True) = ""
    groupid: constr(max_length=100, strip_whitespace=True)
    votes: int | None
    members: list[str] = []
    post_as: bool = False
    show_on_speaker: bool = True
    delegate_to: str | None = None

    @validator("title", pre=True, allow_reuse=True)
    def strip_group_title_html(cls, v):
        return strip_html(v) if isinstance(v, str) else v

    @validator("body", pre=True, allow_reuse=True)
    def clean_group_body(cls, v):
        return strict_clean_html(v) if isinstance(v, str) else v

    @validator("title")
    def use_groupid_as_title_if_empty(cls, v, values: dict):
        if not v:
            v = values["groupid"]
        return v

    @validator("members", pre=True)
    def fetch_members(cls, v):
        if isinstance(v, (models.QuerySet, models.Manager)):
            return list(v.values_list("username", flat=True))
        return v

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

    @validator("title", pre=True, allow_reuse=True)
    def strip_ai_title_html(cls, v):
        return strip_html(v) if isinstance(v, str) else v

    @validator("body", pre=True, allow_reuse=True)
    def clean_ai_body(cls, v):
        return strict_clean_html(v) if isinstance(v, str) else v

    @validator("text_documents", pre=True)
    def fetch_related_text(cls, v):
        return resolve_potential_manager(v)

    @validator("proposals", pre=True)
    def fetch_related_proposals(cls, v):
        ctx = get_context()
        if not ctx.include_proposals:
            return []
        return resolve_potential_manager(v, select={"meeting_group", "author"})

    @validator("discussions", pre=True)
    def fetch_related_qs(cls, v):
        ctx = get_context()
        if not ctx.include_discussions:
            return []
        return resolve_potential_manager(v, select={"meeting_group", "author"})

    @validator("proposals", pre=True)
    def select_proposal_type(cls, v: list[dict | ProposalData | DiffProposalData]):
        """
        Duck-type dict data as a proposal
        >>> f = AgendaItemData.select_proposal_type
        >>> result = f([{'body': 'Hello', 'pk': 3}, {'body': 'World', 'text_document': 'hi', 'paragraph': 2}, ProposalData(body="Unchanged")])
        >>> result[0]
        ProposalData(meeting_group=None, as_group=False, author=None, body='Hello', created=None, modified=None, tags=[], pk='_3', state=None, prop_id=None)
        >>> result[1]
        DiffProposalData(meeting_group=None, as_group=False, author=None, body='World', created=None, modified=None, tags=[], pk=None, state=None, prop_id=None, text_document='hi', paragraph=2)
        >>> result[2]
        ProposalData(meeting_group=None, as_group=False, author=None, body='Unchanged', created=None, modified=None, tags=[], pk=None, state=None, prop_id=None)
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
        >>> AgendaItemData.check_state("upcoming")
        'upcoming'
        >>> with schema_context(clear_ai_states=True):
        ...     AgendaItemData.check_state("upcoming") == None
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
        if v and v not in {s.value for s in AgendaItemStateMachine.states}:
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


class MeetingStructure(BaseModel):
    groups: list[MeetingGroupData] = []
    agenda_items: list[AgendaItemData] = []
    reaction_buttons: list[ReactionButtonData] = []
    notes: list[NoteData] = []

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

    @validator("reaction_buttons", pre=True)
    def fetch_reaction_buttons(cls, v):
        ctx = get_context()
        if not ctx.include_buttons:
            return []
        return resolve_potential_manager(v)

    @validator("notes", pre=True)
    def fetch_notes(cls, v):
        ctx = get_context()
        if not ctx.include_notes:
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
    if isinstance(v, (models.Manager, models.QuerySet)):
        if hasattr(v, "select_subclasses"):
            v = v.select_subclasses()
        if prefetch:
            v = v.prefetch_related(*prefetch)
        if select:
            v = v.select_related(*select)
        ctx = get_context()
        return [
            ctx.model_to_schema[o.__class__].from_orm(o) for o in v.all().order_by("id")
        ]
    return v


model_to_schema = {
    AgendaItem: AgendaItemData,
    MeetingGroup: MeetingGroupData,
    TextDocument: TextDocumentData,
    Proposal: ProposalData,
    DiffProposal: DiffProposalData,
    DiscussionPost: DiscussionPostData,
    ReactionButton: ReactionButtonData,
    Reaction: ReactionData,
    Note: NoteData,
}


class ImportStats(BaseModel):
    agenda_items: int = 0
    groups: int = 0
    proposals: int = 0
    diff_proposals: int = 0
    discussion_posts: int = 0
    text_documents: int = 0
    buttons: int = 0
    reactions: int = 0
    groups_reused: int = 0
    buttons_reused: int = 0
    notes: int = 0


class ImportMeetingMeta(BaseModel):
    version: int
    created: datetime | None
    title: str = ""
    description: str = ""

    @validator("title", "description", pre=True, allow_reuse=True)
    def strip_html_from_meta(cls, v):
        return strip_html(v) if isinstance(v, str) else v


class ImportMeetingStructure(MeetingStructure):
    meta: ImportMeetingMeta | None


class ExportMeetingMeta(BaseModel):
    version: int = 1
    created: datetime = now()
    title: str = ""
    description: str = ""


class ExportMeetingStructure(MeetingStructure):
    meta: ExportMeetingMeta = Field(default_factory=ExportMeetingMeta)
