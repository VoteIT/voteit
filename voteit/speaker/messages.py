from __future__ import annotations

from abc import ABC
from datetime import datetime

from typing import List
from typing import Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext as _
from pydantic.main import BaseModel

from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.abcs import ContextAction
from voteit.messaging.abcs import DeferredJob
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.messaging.errors import BadRequestError
from voteit.messaging.errors import NotFoundError
from voteit.messaging.errors import ValidationErrorMsg
from voteit.messaging.messages.base import BaseObjectDeleted
from voteit.messaging.messages.status import StatusDone
from voteit.speaker.models import SpeakerList
from voteit.speaker.permissions import SpeakerListPermissions
from voteit.speaker.rules import not_currently_speaking


class SpeakerListActionSchema(BaseModel):
    pk: int  # which list to perform the action on


class SpeakerListUserSchema(SpeakerListActionSchema):
    userid: int  # Moderators may also enter someone else.


class ListMessage(BaseIncomingMessage, DeferredJob, ContextAction[SpeakerList], ABC):
    model = SpeakerList
    schema = SpeakerListActionSchema
    data: SpeakerListActionSchema
    context_pk_attr = "pk"


class ModeratorListMessage(
    BaseIncomingMessage, DeferredJob, ContextAction[SpeakerList], ABC
):
    model = SpeakerList
    schema = SpeakerListUserSchema
    data: SpeakerListUserSchema
    context_pk_attr = "pk"

    def get_user(self) -> AbstractUser:
        User = get_user_model()
        try:
            return User.objects.get(pk=self.data.userid)
        except User.DoesNotExist:
            raise NotFoundError.from_message(
                self, msg=_("No user with pk %(pk)s") % {"pk": self.data.pk}
            )


@incoming
class SpeakerListEnter(ListMessage):
    name = "speaker_list.enter"
    permission = SpeakerListPermissions.ENTER

    def run_job(self) -> StatusDone:
        self.assert_perm()
        existing_obj = self.context.speaker_items.filter(
            user=self.user, order__isnull=False
        ).first()
        if existing_obj is not None:
            raise BadRequestError.from_message(self, msg=_("Already in list"))
        self.context.speaker_items.create(user=self.user)
        msg = StatusDone.from_message(self)
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


@incoming
class SpeakerListLeave(ListMessage):
    name = "speaker_list.leave"
    permission = SpeakerListPermissions.LEAVE

    def run_job(self) -> StatusDone:
        self.assert_perm()
        existing_obj = self.context.speaker_items.filter(
            user=self.user, order__isnull=False
        ).first()
        if existing_obj is None:
            raise BadRequestError.from_message(self, msg=_("Not in list"))
        existing_obj.delete()
        msg = StatusDone.from_message(self)
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


@incoming
class SetActiveList(ListMessage):
    name = "speaker_list.set_active"
    permission = SpeakerListPermissions.CHANGE

    def run_job(self) -> StatusDone:
        self.assert_perm()
        system = self.context.speaker_system
        if not self.context.is_active_list:
            if system.active_list and system.active_list.current is not None:
                raise ValidationErrorMsg.from_message(
                    self,
                    msg=_("Another list has an active speaker."),
                    errors=[
                        {
                            "loc": ("pk",),
                            "msg": _(
                                "List '%(title)s' with id %(id)s is active"
                                % {
                                    "title": system.active_list.title,
                                    "id": system.active_list,
                                }
                            ),
                            "type": "value.error",
                        }
                    ],
                )
            system.active_list = self.context
            system.save()
            msg = StatusDone.from_message(self)
            msg.send_outgoing(self.mm.consumer_name, success=True)
            return msg


@incoming
class StartSpeakerInList(ModeratorListMessage):
    """Start userid. Ignore if not found or already speaking."""

    name = "speaker_list.start_user"
    permission = SpeakerListPermissions.START

    def run_job(self) -> StatusDone:
        self.assert_perm()
        user = self.get_user()
        speaker = self.context.speaker_items.filter(
            user=user, order__isnull=False
        ).first()
        if speaker is None:
            raise ValidationErrorMsg.from_message(
                self,
                msg=_("No such user in queue."),
                errors=[
                    {
                        "loc": ("userid",),
                        "msg": _("user_pk %s not in queue") % user.pk,
                        "type": "value.error",
                    }
                ],
            )
        self.context.start_speaker(speaker)
        self.context.signal_list_updated()
        msg = StatusDone.from_message(self)
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


@incoming
class StopSpeakerInList(ModeratorListMessage):
    """Stop userid. Ignore if not speaking."""

    name = "speaker_list.stop_user"
    permission = SpeakerListPermissions.STOP

    def run_job(self) -> StatusDone:
        self.assert_perm()
        user = self.get_user()
        speaker = self.context.current
        if speaker is None:
            raise ValidationErrorMsg.from_message(
                self,
                msg=_("No current speaker"),
                errors=[
                    {
                        "loc": ("userid",),
                        "msg": "",
                        "type": "value.error",
                    }
                ],
            )
        if user != speaker.user:
            raise ValidationErrorMsg.from_message(
                self,
                msg=_("That user isn't speaking."),
                errors=[
                    {
                        "loc": ("userid",),
                        "msg": _("user_pk %s") % user.pk,
                        "type": "value.error",
                    }
                ],
            )
        self.context.stop_speaker()
        self.context.signal_list_updated()
        msg = StatusDone.from_message(self)
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


class SpeakerStatsSchema(BaseModel):
    pk: int  # Speaker pk
    userid: int  # User speaker
    speaker_list: int
    started: Optional[datetime]
    seconds: Optional[int]


@outgoing
class SpeakerStarted(BaseOutgoingMessage):
    name = "speaker.started"
    schema = SpeakerStatsSchema
    data: SpeakerStatsSchema


@outgoing
class SpeakerStopped(BaseOutgoingMessage):
    name = "speaker.stopped"
    schema = SpeakerStatsSchema
    data: SpeakerStatsSchema


@incoming
class ModeratorSpeakerListEnter(ModeratorListMessage):
    name = "speaker_list.mod_enter"
    # Note permission diff: Perms will be checked against moderator
    permission = SpeakerListPermissions.CHANGE

    def run_job(self) -> StatusDone:
        self.assert_perm()
        user = self.get_user()
        # Negating rules has unwanted side-effects, hence this silly thing :)
        if not not_currently_speaking(user, self.context):
            raise BadRequestError.from_message(self, msg=_("Currently speaking"))
        if self.context.meeting is not None:
            if not self.context.meeting.has_roles(user, ROLE_PARTICIPANT):
                raise BadRequestError.from_message(
                    self, msg=_("User isn't part of this meeting")
                )

        existing_obj = self.context.speaker_items.filter(
            user=user, order__isnull=False
        ).first()
        if existing_obj is not None:
            raise BadRequestError.from_message(self, msg=_("Already in list"))
        self.context.speaker_items.create(user=user)
        msg = StatusDone.from_message(self)
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


@incoming
class ModeratorSpeakerListLeave(ModeratorListMessage):
    name = "speaker_list.mod_leave"
    # Note permission diff: Perms will be checked against moderator
    permission = SpeakerListPermissions.CHANGE

    def run_job(self) -> StatusDone:
        self.assert_perm()
        user = self.get_user()
        existing_obj = self.context.speaker_items.filter(
            user=user, order__isnull=False
        ).first()
        if existing_obj is None:
            raise BadRequestError.from_message(self, msg=_("Not in list"))
        existing_obj.delete()
        msg = StatusDone.from_message(self)
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


@incoming
class ModeratorSpeakerListUndo(ListMessage):
    name = "speaker_list.mod_undo"
    permission = SpeakerListPermissions.STOP

    def run_job(self) -> StatusDone:
        self.assert_perm()
        if not self.context.undo_speaker():
            raise BadRequestError.from_message(self, msg=_("No active speaker"))
        msg = StatusDone.from_message(self)
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


@incoming
class ModeratorSpeakerListShuffle(ListMessage):
    name = "speaker_list.mod_shuffle"
    permission = SpeakerListPermissions.CHANGE

    def run_job(self) -> StatusDone:
        self.assert_perm()
        self.context.shuffle()
        msg = StatusDone.from_message(self)
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


class OrderSchema(BaseModel):
    pk: int  # speaker list pk
    queue: List[int]  # user pks, unique values
    history: List[List[int]]  # List of [User pk, seconds] in descending spoken order
    current: Optional[int]  # current user pk if speaker


@outgoing
class SpeakerListOrder(BaseOutgoingMessage):
    name = "speaker_list.order"
    schema = OrderSchema
    data: OrderSchema


class SpeakerListSchema(BaseModel):
    title: Optional[str]
    pk: int
    state: str
    speaker_system: int  # pk
    agenda_item: Optional[int]  # pk


@outgoing
class SpeakerListAdded(BaseOutgoingMessage):
    name = "speaker_list.added"
    schema = SpeakerListSchema
    data: SpeakerListSchema


@outgoing
class SpeakerListChanged(BaseOutgoingMessage):
    name = "speaker_list.changed"
    schema = SpeakerListSchema
    data: SpeakerListSchema


@outgoing
class SpeakerListDeleted(BaseObjectDeleted):
    name = "speaker_list.deleted"


class SpeakerSystemSchema(BaseModel):
    pk: int
    state: str
    title: Optional[str]
    meeting: Optional[int]
    method_name: str
    settings: Optional[dict]
    safe_positions: Optional[int]
    active_list: Optional[int]
    meeting_roles_to_speaker: List[str]


@outgoing
class SpeakerSystemAdded(BaseOutgoingMessage):
    name = "speaker_system.added"
    schema = SpeakerSystemSchema
    data: SpeakerSystemSchema


@outgoing
class SpeakerSystemChanged(BaseOutgoingMessage):
    name = "speaker_system.changed"
    schema = SpeakerSystemSchema
    data: SpeakerSystemSchema


@outgoing
class SpeakerSystemDeleted(BaseObjectDeleted):
    name = "speaker_system.deleted"
