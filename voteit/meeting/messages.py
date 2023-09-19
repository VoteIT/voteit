from logging import getLogger

from auditlog.context import set_actor
from django.utils.text import slugify
from pydantic import BaseModel
from pydantic import conint
from pydantic import conlist
from pydantic import constr
from pydantic import validator

from envelope.deferred_jobs.message import ContextAction
from envelope.messages.common import Status
from envelope.messages.errors import UnauthorizedError
from envelope.utils import websocket_send
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.utils import clone_meeting
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing


logger = getLogger(__name__)


@outgoing
class MeetingChanged(BaseObjectChanged):
    name = "meeting.changed"


@outgoing
class MeetingDeleted(BaseObjectDeleted):
    name = "meeting.deleted"


@outgoing
class MeetingGroupAdded(BaseObjectAdded):
    name = "meeting_group.added"


@outgoing
class MeetingGroupChanged(BaseObjectChanged):
    name = "meeting_group.changed"


@outgoing
class MeetingGroupDeleted(BaseObjectDeleted):
    name = "meeting_group.deleted"


@outgoing
class GroupRoleAdded(BaseObjectAdded):
    name = "group_role.added"


@outgoing
class GroupRoleChanged(BaseObjectChanged):
    name = "group_role.changed"


@outgoing
class GroupRoleDeleted(BaseObjectDeleted):
    name = "group_role.deleted"


@outgoing
class GroupMembershipAdded(BaseObjectAdded):
    name = "group_membership.added"


@outgoing
class GroupMembershipChanged(BaseObjectChanged):
    name = "group_membership.changed"


@outgoing
class GroupMembershipDeleted(BaseObjectDeleted):
    name = "group_membership.deleted"


class CopyMeetingSchema(BaseModel):
    meeting: int
    # Settings etc later on


@incoming
class CopyMeeting(ContextAction):
    name = "meeting.create_copy"
    permission = MeetingPermissions.VIEW
    schema = CopyMeetingSchema
    data: CopyMeetingSchema
    model = Meeting
    context_schema_attr = "meeting"

    def run_job(self):
        # Read meeting
        self.assert_perm()
        organisation = self.user.organisation
        assert organisation
        # Double permission check here, since add is needed too
        if not self.user.has_perm(MeetingPermissions.ADD, organisation):
            raise UnauthorizedError.from_message(
                self,
                model=organisation.__class__,
                key="pk",
                value=organisation.pk,
                permission=MeetingPermissions.ADD,
            )
        meeting: Meeting = self.context
        update = Status.from_message(self)
        websocket_send(update, state=update.RUNNING, on_commit=False)
        with set_actor(self.user):
            clone_meeting(meeting, user=self.user)
        websocket_send(update, state=update.SUCCESS)


class MeetingGroupSchema(BaseModel):
    title: constr(strip_whitespace=True, max_length=100)
    groupid: constr(to_lower=True, min_length=1, max_length=100, strip_whitespace=True)
    votes: int | None

    @validator("groupid", pre=True)
    def transform_groupid(cls, v: str):
        return slugify(v)


class CreateMeetingGroupsSchema(BaseModel):
    r"""
    >>> groups = [MeetingGroupSchema(title=x, groupid=x) for x in range(251)]
    >>> CreateMeetingGroupsSchema(meeting=1, groups=groups)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 1 validation error for CreateMeetingGroupsSchema
    groups
      ensure this value has at most 250 items (type=value_error.list.max_items; limit_value=250)
    >>> CreateMeetingGroupsSchema(groups="a\tA\t\nB\tB\t1", meeting=1)
    CreateMeetingGroupsSchema(meeting=1, groups=[MeetingGroupSchema(title='a', groupid='a', votes=None), MeetingGroupSchema(title='B', groupid='b', votes=1)])
    """

    meeting: conint(ge=1)
    groups: conlist(MeetingGroupSchema, unique_items=True, max_items=250, min_items=1)

    @validator("groups", pre=True)
    def transform_to_groups(cls, v: str | list):
        r"""
        >>> f =  CreateMeetingGroupsSchema.transform_to_groups
        >>> f("a\tA\t\nB\tB\t1")
        [{'title': 'a', 'groupid': 'A'}, {'title': 'B', 'groupid': 'B', 'votes': '1'}]
        """
        if isinstance(v, str):

            def _tc(title=None, groupid=None, votes=None, *args):
                if votes:
                    return {"title": title, "groupid": groupid, "votes": votes}
                return {"title": title, "groupid": groupid}

            new_list = []
            for row in v.splitlines():
                items = row.split("\t")
                if items:
                    new_list.append(_tc(*items))
            return new_list
        return v

    @validator("groups")
    def validate_unique_group_items(cls, v: list[MeetingGroupSchema]):
        """
        >>> f = CreateMeetingGroupsSchema.validate_unique_group_items
        >>> MGS = MeetingGroupSchema
        >>> items = [MGS(title=x, groupid=x) for x in ['a', 'b']]
        >>> f(items)
        [MeetingGroupSchema(title='a', groupid='a', votes=None), \
            MeetingGroupSchema(title='b', groupid='b', votes=None)]
        >>> items = [MGS(title=x, groupid=x) for x in ['a', 'A b']]
        >>> f(items)
        [MeetingGroupSchema(title='a', groupid='a', votes=None), \
            MeetingGroupSchema(title='A b', groupid='a-b', votes=None)]

        >>> items = [MGS(title=x, groupid=x) for x in ['a', 'A']]
        >>> f(items)
        Traceback (most recent call last):
        ...
        ValueError: The following lines have duplicated values: 2
        """
        found_titles = set()
        found_ids = set()
        non_unique_title_rows = []
        non_unique_id_rows = []
        for i, item in enumerate(v, 1):
            if item.groupid in found_ids:
                non_unique_id_rows.append(i)
            found_ids.add(item.groupid)
            if item.title.lower() in found_titles:
                non_unique_title_rows.append(i)
            found_titles.add(item.title.lower())
        if non_unique_title_rows or non_unique_id_rows:
            err_txt = "There were errors with groups:\n"
            if non_unique_title_rows:
                err_txt += (
                    "These lines have titles that aren't unique: %s\n"
                    % ", ".join(str(x) for x in non_unique_title_rows)
                )
            if non_unique_id_rows:
                err_txt += (
                    "These lines have groupids that aren't unique: %s\n"
                    % ", ".join(str(x) for x in non_unique_id_rows)
                )
            raise ValueError(err_txt)
        return v


@incoming
class CreateMeetingGroups(ContextAction):
    name = "meeting_group.bulk_create"
    permission = MeetingPermissions.CHANGE
    schema = CreateMeetingGroupsSchema
    data: CreateMeetingGroupsSchema
    model = Meeting
    context_schema_attr = "meeting"

    def run_job(self):
        self.assert_perm()
        update = Status.from_message(self)
        websocket_send(update, state=update.RUNNING, on_commit=False)
        created_count = 0
        updated_count = 0
        with set_actor(self.user):
            for gdata in self.data.groups:
                group, created = self.context.groups.update_or_create(
                    groupid=gdata.groupid,
                    defaults={"votes": gdata.votes, "title": gdata.title},
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1
        logger.info(
            "Group changes - created: %s, updated: %s", created_count, updated_count
        )
        websocket_send(update, state=update.SUCCESS)
        return update
