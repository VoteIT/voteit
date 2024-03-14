from itertools import chain
from uuid import uuid4

import yaml
from django.contrib.auth import get_user_model

from voteit.agenda.models import AgendaItem
from voteit.core.decorators import ensure_atomic
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.proposal.models import DiffProposal
from voteit.proposal.models import TextDocument
from voteit.export_import import MissingUser
from voteit.export_import import schemas

User = get_user_model()

__all__ = (
    "Importer",
    "ImportFileError",
)


class ImportFileError(Exception): ...


class Importer:
    version = 1
    data: schemas.MeetingStructure = None

    def __init__(
        self,
        meeting: Meeting,
        schema: type[schemas.MeetingStructure] = schemas.MeetingStructure,
        user_map_attr="email",
        missing_user: str = MissingUser.RAISE,
        add_participants: bool = True,
        **kwargs,
    ):
        assert missing_user in (
            MissingUser.RAISE,
            MissingUser.CREATE,
            MissingUser.BLANK,
        )
        assert isinstance(meeting, Meeting)
        self.meeting = meeting
        self.schema = schema
        self.organisation = meeting.organisation
        # Config
        self.missing_user_strategy = missing_user
        self.add_participants = add_participants
        self.user_map_attr = user_map_attr
        self.export_schema_kwargs = kwargs
        # Internal data
        self.mg_map = {}
        self.user_map = {}

    def prepare(self, data: dict):
        with schemas.schema_context(**self.export_schema_kwargs):
            self.data = self.schema(**data)

    def run(self):
        self.collect_users()
        self.populate()

    def from_file(self, fn):
        with open(fn, "r") as fs:
            return self.from_stream(fs)

    def from_stream(self, stream):
        data = yaml.safe_load(stream)
        if not isinstance(data, dict):
            raise ImportFileError("Import file malformed, must be key-value data")
        try:
            version = data["meta"]["version"]
        except KeyError:
            raise ImportFileError("yaml file malformed, lacks meta version")
        if version != self.version:
            raise ImportFileError("Wrong file version, must be %s" % self.version)
        with schemas.schema_context(**self.export_schema_kwargs):
            self.data = self.schema(**data)

    @ensure_atomic
    def collect_users(self):
        users = set()
        for mgd in self.data.groups:
            users.update(mgd.members)
        for aid in self.data.agenda_items:
            for obj in chain(aid.proposals, aid.discussions):
                if obj.author:
                    users.add(obj.author)
        user_search_attrs = {getattr(x, self.user_map_attr) for x in users}
        user_qs = (
            self.organisation.users.exclude(is_active=False)
            .filter(**{f"{self.user_map_attr}__in": user_search_attrs})
            .order_by("-last_login")
        )
        # Order by last_login to fetch active users first in case of duplicates
        existing_vals = set(user_qs.values_list(self.user_map_attr, flat=True))
        missing = user_search_attrs - existing_vals
        if missing:
            if self.missing_user_strategy == MissingUser.CREATE:
                create_users = {
                    x for x in users if getattr(x, self.user_map_attr) in missing
                }
                for userd in create_users:
                    user_kwargs = userd.dict(exclude={"pk"})
                    if userd.email:
                        user_kwargs.setdefault(
                            "first_name", userd.email.split("@")[0].title()
                        )
                    user_kwargs.setdefault("username", str(uuid4()))
                    user = self.organisation.users.create(**user_kwargs)
                    self.user_map[getattr(user, self.user_map_attr)] = user
            elif self.missing_user_strategy == MissingUser.BLANK:
                for v in missing:
                    self.user_map[v] = None
            else:
                # Raise is default
                raise User.DoesNotExist(
                    "Can't find users with the following data:\n%s" % "\n".join(missing)
                )
        for user in user_qs:
            self.user_map[getattr(user, self.user_map_attr)] = user

    def convert_fks(self, data: dict) -> dict:
        if meeting_group_id := data.get("meeting_group"):
            data["meeting_group"] = self.mg_map[meeting_group_id]
        if user_data := data.get("author"):
            data["author"] = self.user_map[user_data[self.user_map_attr]]
        return data

    @ensure_atomic
    def populate(self):
        # FIXME: This requires proper validation before allowing it to be used via frontend
        # Groups
        for mgd in self.data.groups:
            group: MeetingGroup = self.meeting.groups.create(
                **mgd.dict(exclude={"members"}, exclude_none=True)
            )
            self.mg_map[group.groupid] = group
            if mgd.members:
                members = set()
                for userd in mgd.members:
                    if user := self.user_map[getattr(userd, self.user_map_attr)]:
                        members.add(user.pk)
                if members:
                    group.members.add(*members)
        aid_exclude = {"text_documents", "proposals", "discussions"}
        for aid in self.data.agenda_items:
            ai: AgendaItem = self.meeting.agenda_items.create(
                **aid.dict(exclude=aid_exclude, exclude_none=True)
            )
            ai_text_base_tag_map = {}
            # Text documents
            for tdd in aid.text_documents:
                td_data = self.convert_fks(tdd.dict())
                text_document: TextDocument = ai.text_documents.create(**td_data)
                ai_text_base_tag_map[text_document.base_tag] = text_document
            # Proposals
            for propd in aid.proposals:
                prop_data = self.convert_fks(
                    propd.dict(exclude={"text_document"}, exclude_none=True)
                )
                if isinstance(propd, schemas.DiffProposalData):
                    text_document = ai_text_base_tag_map[propd.text_document]
                    prop_data["paragraph"] = text_document.text_paragraphs.get(
                        paragraph_id=propd.paragraph
                    )
                    DiffProposal.objects.create(agenda_item=ai, **prop_data)
                else:
                    ai.proposals.create(**prop_data)
            # Discussions
            for discd in aid.discussions:
                disc_data = self.convert_fks(discd.dict())
                ai.discussions.create(**disc_data)
        if self.add_participants:
            users = {
                x for x in self.user_map.values() if x
            }  # Can be None in some cases
            existing_participant_pks = set(
                self.meeting.participants.filter(
                    pk__in={x.pk for x in users}
                ).values_list("pk", flat=True)
            )
            for user in users:
                if user.pk in existing_participant_pks:
                    continue
                self.meeting.add_roles(user, ROLE_PARTICIPANT)

    def __len__(self):
        if self.data:
            return len(self.data.agenda_items) + len(self.data.groups)
        return 0

    def stats(self) -> schemas.ImportStats:
        stats = schemas.ImportStats(
            agenda_items=len(self.data.agenda_items), groups=len(self.data.groups)
        )
        for ai in self.data.agenda_items:
            stats.diff_proposals += len(
                [x for x in ai.proposals if isinstance(x, schemas.DiffProposalData)]
            )
            stats.proposals += len(
                [x for x in ai.proposals if isinstance(x, schemas.ProposalData)]
            )
            stats.discussion_posts += len(ai.discussions)
            stats.text_documents += len(ai.text_documents)
        return stats
