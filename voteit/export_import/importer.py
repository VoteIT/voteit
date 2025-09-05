from itertools import chain

import yaml
from django.contrib.auth import get_user_model

from voteit.agenda.models import AgendaItem
from voteit.core.decorators import ensure_atomic
from voteit.export_import.exceptions import ImportFileError
from voteit.export_import.schemas import ImportMeetingStructure
from voteit.export_import.utils import verify_stream
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.proposal.models import DiffProposal
from voteit.proposal.models import TextDocument
from voteit.export_import import MissingUser
from voteit.export_import import schemas

User = get_user_model()

__all__ = ("Importer",)


class Importer:
    version = 1
    data: ImportMeetingStructure = None

    def __init__(
        self,
        meeting: Meeting,
        schema: type[ImportMeetingStructure] = ImportMeetingStructure,
        user_map_attr="username",
        missing_user: str = MissingUser.RAISE,
        add_participants: bool = True,
        use_existing_groups: bool = True,
        verify=True,
        **kwargs,
    ):
        assert missing_user in (
            MissingUser.RAISE,
            # MissingUser.CREATE,
            MissingUser.BLANK,
        )
        assert isinstance(meeting, Meeting)
        self.meeting = meeting
        self.schema = schema
        self.organisation = meeting.organisation
        # Config
        self.missing_user_strategy = missing_user
        self.add_participants = add_participants
        self.use_existing_groups = use_existing_groups
        self.user_map_attr = user_map_attr
        self.export_schema_kwargs = kwargs
        # Internal data
        self.mg_map = {}
        self.user_map = {}
        self.ai_map = {}
        self.prop_map = {}
        self.diff_prop_map = {}
        self.disc_map = {}
        self.button_map = {}
        self._verify = verify
        self.groups_reused = 0
        self.buttons_reused = 0

    def run(self):
        self.collect_users()
        self.populate()

    __call__ = run

    def from_file(self, fn):
        with open(fn, "r") as fs:
            return self.from_stream(fs)

    def from_stream(self, stream):
        if self._verify:
            verify_stream(stream)
            stream.seek(0)
        data = yaml.safe_load(stream)
        if not isinstance(data, dict):
            raise ImportFileError("Import file malformed, must be key-value data")
        try:
            version = data["meta"]["version"]
        except KeyError:
            raise ImportFileError("yaml file malformed, lacks meta version")
        if version != self.version:
            raise ImportFileError("Wrong file version, must be %s" % self.version)
        self.prep_data(data)

    def prep_data(self, data: dict):
        if self.data is not None:
            raise Exception("Already prepped")
        with schemas.schema_context(**self.export_schema_kwargs):
            self.data = self.schema(**data)

    @ensure_atomic
    def collect_users(self):
        user_identifiers = set()
        for mgd in self.data.groups:
            user_identifiers.update(mgd.members)
        for aid in self.data.agenda_items:
            for obj in chain(aid.proposals, aid.discussions):
                if obj.author:
                    user_identifiers.add(obj.author)

        for btn_data in self.data.reaction_buttons:
            user_identifiers.update(
                x.username for x in btn_data.reactions if x.username
            )
        user_qs = (
            self.organisation.users.exclude(is_active=False)
            .filter(**{f"{self.user_map_attr}__in": user_identifiers})
            .order_by("-last_login")
        )
        # Order by last_login to fetch active users first in case of duplicates
        existing_vals = set(user_qs.values_list(self.user_map_attr, flat=True))
        missing = user_identifiers - existing_vals
        if missing:
            if self.missing_user_strategy == MissingUser.BLANK:
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
        if user_identifier := data.get("author"):
            data["author"] = self.user_map[user_identifier]
        return data

    @ensure_atomic
    def populate(self):
        # FIXME: This requires proper validation before allowing it to be used via frontend
        # Groups
        for mgd in self.data.groups:
            if self.use_existing_groups:
                group, _created = self.meeting.groups.update_or_create(
                    groupid=mgd.groupid,
                    defaults=mgd.dict(
                        exclude={"members", "groupid", "pk"}, exclude_none=True
                    ),
                )
                group: MeetingGroup
                if not _created:
                    self.groups_reused += 1

            else:
                group: MeetingGroup = self.meeting.groups.create(
                    **mgd.dict(exclude={"members", "pk"}, exclude_none=True)
                )
            self.mg_map[group.groupid] = group
            if mgd.members:
                members = set()
                for userd in mgd.members:
                    if user := self.user_map[userd]:
                        members.add(user.pk)
                if members:
                    group.members.add(*members)
        for aid in self.data.agenda_items:
            ai: AgendaItem = self.meeting.agenda_items.create(
                **aid.dict(
                    exclude={"text_documents", "proposals", "discussions", "pk"},
                    exclude_none=True,
                )
            )
            self.ai_map[aid.pk] = ai
            ai_text_base_tag_map = {}
            # Text documents
            for tdd in aid.text_documents:
                td_data = self.convert_fks(tdd.dict(exclude={"pk"}))
                text_document: TextDocument = ai.text_documents.create(**td_data)
                ai_text_base_tag_map[text_document.base_tag] = text_document
            # Proposals
            for propd in aid.proposals:
                prop_data = self.convert_fks(
                    propd.dict(exclude={"text_document", "pk"}, exclude_none=True)
                )
                if isinstance(propd, schemas.DiffProposalData):
                    text_document = ai_text_base_tag_map[propd.text_document]
                    prop_data["paragraph"] = text_document.text_paragraphs.get(
                        paragraph_id=propd.paragraph
                    )
                    prop = DiffProposal.objects.create(agenda_item=ai, **prop_data)
                    self.diff_prop_map[propd.pk] = prop
                else:
                    prop = ai.proposals.create(**prop_data)
                    self.prop_map[propd.pk] = prop
            # Discussions
            for discd in aid.discussions:
                disc_data = self.convert_fks(discd.dict(exclude={"pk"}))
                disc = ai.discussions.create(**disc_data)
                self.disc_map[discd.pk] = disc
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
        # Buttons
        for btnd in self.data.reaction_buttons:
            if button := self.meeting.reaction_buttons.filter(
                title__iexact=btnd.title,
                color__iexact=btnd.color,
                icon__iexact=btnd.icon,
            ).first():
                if button.flag_mode != btnd.flag_mode:
                    raise ValueError("Flag mode doesn't match")
                changed = False
                for k, v in btnd.dict(
                    exclude={"pk", "reactions", "title", "color", "icon"}
                ).items():
                    if getattr(button, k) != v:
                        changed = True
                        setattr(button, k, v)
                if changed:
                    button.save()
                self.buttons_reused += 1
            else:
                button = self.meeting.reaction_buttons.create(
                    **btnd.dict(exclude={"pk", "reactions"})
                )

            for reactd in btnd.reactions:
                # FIXME: Die on missing reactions?
                if obj := self.resolve_reaction_generic(
                    reactd.object_id, reactd.content_type
                ):
                    button.reactions.create(
                        agenda_item=self.ai_map[reactd.agenda_item_id],
                        user=self.user_map[reactd.username],
                        object=obj,
                    )
                else:
                    raise Exception(
                        "Can't find object id %s with natural key %s"
                        % (reactd.object_id, reactd.content_type)
                    )

    def resolve_reaction_generic(self, fk: str, natural_key: tuple[str, str]):
        match natural_key:
            case ("proposal", "proposal"):
                return self.prop_map.get(fk)
            case ("proposal", "diffproposal"):
                return self.diff_prop_map.get(fk)
            case ("discussion", "discussionpost"):
                return self.disc_map.get(fk)

    def __len__(self):
        if self.data:
            return len(self.data.agenda_items) + len(self.data.groups)
        return 0

    def stats(self) -> schemas.ImportStats:
        stats = schemas.ImportStats(
            agenda_items=len(self.data.agenda_items),
            groups=len(self.data.groups),
            buttons=len(self.data.reaction_buttons),
            buttons_reused=self.buttons_reused,
            groups_reused=self.groups_reused,
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
        for btn in self.data.reaction_buttons:
            stats.reactions += len(btn.reactions)
        return stats
