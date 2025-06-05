from __future__ import annotations

from abc import ABC

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext as _
from pydantic.main import BaseModel
from auditlog.context import set_actor
from envelope.deferred_jobs.message import ContextAction
from envelope.messages.common import Status
from envelope.messages.errors import BadRequestError
from envelope.messages.errors import NotFoundError
from envelope.messages.errors import ValidationErrorMsg
from envelope.utils import websocket_send

from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.speaker.models import SpeakerList
from voteit.speaker.permissions import SpeakerListPermissions
from voteit.speaker.rules import not_currently_speaking
from voteit.speaker.workflows import SpeakerListWf


class SpeakerListActionSchema(BaseModel):
    pk: int  # which list to perform the action on


class SpeakerListUserSchema(SpeakerListActionSchema):
    user: int  # Moderators may also enter someone else.


class ListMessage(ContextAction, ABC):
    model = SpeakerList
    schema = SpeakerListActionSchema
    data: SpeakerListActionSchema


class ModeratorListMessage(ContextAction, ABC):
    model = SpeakerList
    schema = SpeakerListUserSchema
    data: SpeakerListUserSchema

    def get_user(self) -> AbstractUser:
        User = get_user_model()
        try:
            return User.objects.get(pk=self.data.user)
        except User.DoesNotExist:
            raise NotFoundError.from_message(
                self,
                msg=_("No user with pk %(pk)s") % {"pk": self.data.pk},
                model=self.model,
                value=self.data.user,
            )


@incoming
class SpeakerListEnter(ListMessage):
    name = "speaker_list.enter"
    permission = SpeakerListPermissions.ENTER

    def run_job(self) -> Status:
        self.assert_perm()
        existing_obj = self.context.speakers_in_queue().filter(user=self.user).first()
        if existing_obj is not None:
            raise BadRequestError.from_message(self, msg=_("Already in list"))
        self.context.speaker_items.create(user=self.user)
        msg = Status.from_message(self)
        websocket_send(msg, state=msg.SUCCESS)
        return msg


@incoming
class SpeakerListLeave(ListMessage):
    name = "speaker_list.leave"
    permission = SpeakerListPermissions.LEAVE

    def run_job(self) -> Status:
        self.assert_perm()
        existing_obj = self.context.speakers_in_queue().filter(user=self.user).first()
        if existing_obj is None:
            raise BadRequestError.from_message(self, msg=_("Not in list"))
        existing_obj.delete()
        self.context.reorder()
        msg = Status.from_message(self)
        websocket_send(msg, state=msg.SUCCESS)
        return msg


@incoming
class SetActiveList(ListMessage):
    name = "speaker_list.set_active"
    permission = SpeakerListPermissions.CHANGE

    def run_job(self) -> Status:
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
            with set_actor(self.user):
                system.active_list = self.context
                system.save()
            msg = Status.from_message(self)
            websocket_send(msg, state=msg.SUCCESS)
            return msg


class DeactivateListSchema(SpeakerListActionSchema):
    close_list: bool = False


@incoming
class DeactivateList(ListMessage):
    name = "speaker_list.deactivate"
    permission = SpeakerListPermissions.CHANGE
    model = SpeakerList
    schema = DeactivateListSchema
    data: DeactivateListSchema

    def run_job(self) -> Status:
        self.assert_perm()
        if self.context.is_active_list:
            if self.context.current is not None:
                raise ValidationErrorMsg.from_message(
                    self,
                    msg=_("A speaker is currently speaking."),
                    errors=[
                        {
                            "loc": ("sls",),
                            "msg": _(
                                "List '%(title)s' has an active speaker"
                                % {
                                    "title": self.context.title,
                                }
                            ),
                            "type": "value.error",
                        }
                    ],
                )
            with set_actor(self.user):
                self.context.speaker_system.active_list = None
                self.context.speaker_system.save()
                if self.data.close_list and self.context.state != SpeakerListWf.CLOSED:
                    self.context.close()
                self.context.save()

        # Yes, indentation is correct. We'll want to send thumbs up even if nothing was done. No need to raise alarms.
        msg = Status.from_message(self)
        websocket_send(msg, state=msg.SUCCESS)
        return msg


@incoming
class StartSpeakerInList(ModeratorListMessage):
    """
    Start user. Ignore if not found or already speaking.
    """

    name = "speaker_list.start_user"
    permission = SpeakerListPermissions.START

    def run_job(self) -> Status:
        self.assert_perm()
        user = self.get_user()
        speaker = self.context.speakers_in_queue().filter(user=user).first()
        if speaker is None:
            raise ValidationErrorMsg.from_message(
                self,
                msg=_("No such user in queue."),
                errors=[
                    {
                        "loc": ("user",),
                        "msg": _("user_pk %s not in queue") % user.pk,
                        "type": "value.error",
                    }
                ],
            )
        self.context.start_speaker(speaker)
        msg = Status.from_message(self)
        websocket_send(msg, state=msg.SUCCESS)
        return msg


@incoming
class StopSpeakerInList(ListMessage):
    """
    Stop user. Ignore if not speaking.
    """

    name = "speaker_list.stop_user"
    permission = SpeakerListPermissions.STOP

    def run_job(self) -> Status:
        self.assert_perm()
        self.context.stop_speaker()
        msg = Status.from_message(self)
        websocket_send(msg, state=msg.SUCCESS)
        return msg


@incoming
class ModeratorSpeakerListEnter(ModeratorListMessage):
    name = "speaker_list.mod_enter"
    # Note permission diff: Perms will be checked against moderator
    permission = SpeakerListPermissions.CHANGE

    def run_job(self) -> Status:
        self.assert_perm()
        user = self.get_user()
        # Negating rules has unwanted side effects, hence this silly thing :)
        if not not_currently_speaking(user, self.context):
            raise BadRequestError.from_message(self, msg=_("Currently speaking"))
        if self.context.meeting is not None:
            if not self.context.meeting.has_roles(user, ROLE_PARTICIPANT):
                raise BadRequestError.from_message(
                    self, msg=_("User isn't part of this meeting")
                )
        existing_obj = self.context.speakers_in_queue().filter(user=user).first()
        if existing_obj is not None:
            raise BadRequestError.from_message(self, msg=_("Already in list"))
        self.context.speaker_items.create(user=user)
        msg = Status.from_message(self)
        websocket_send(msg, state=msg.SUCCESS)
        return msg


@incoming
class ModeratorSpeakerListLeave(ModeratorListMessage):
    name = "speaker_list.mod_leave"
    # Note permission diff: Perms will be checked against moderator
    permission = SpeakerListPermissions.CHANGE

    def run_job(self) -> Status:
        self.assert_perm()
        user = self.get_user()
        existing_obj = self.context.speakers_in_queue().filter(user=user).first()
        if existing_obj is None:
            raise BadRequestError.from_message(self, msg=_("Not in list"))
        existing_obj.delete()
        self.context.reorder()
        msg = Status.from_message(self)
        websocket_send(msg, state=msg.SUCCESS)
        return msg


@incoming
class ModeratorSpeakerListUndo(ListMessage):
    name = "speaker_list.mod_undo"
    permission = SpeakerListPermissions.STOP

    def run_job(self) -> Status:
        self.assert_perm()
        if not self.context.undo_speaker():
            raise BadRequestError.from_message(self, msg=_("No active speaker"))
        msg = Status.from_message(self)
        websocket_send(msg, state=msg.SUCCESS)
        return msg


@incoming
class ModeratorSpeakerListShuffle(ListMessage):
    name = "speaker_list.mod_shuffle"
    permission = SpeakerListPermissions.CHANGE

    def run_job(self) -> Status:
        self.assert_perm()
        self.context.shuffle()
        msg = Status.from_message(self)
        websocket_send(msg, state=msg.SUCCESS)
        return msg


@outgoing
class SpeakerListAdded(BaseObjectAdded):
    name = "speaker_list.added"


@outgoing
class SpeakerListChanged(BaseObjectChanged):
    name = "speaker_list.changed"


@outgoing
class SpeakerListDeleted(BaseObjectDeleted):
    name = "speaker_list.deleted"


@outgoing
class SpeakerSystemAdded(BaseObjectAdded):
    name = "speaker_system.added"


@outgoing
class SpeakerSystemChanged(BaseObjectChanged):
    name = "speaker_system.changed"


@outgoing
class SpeakerSystemDeleted(BaseObjectDeleted):
    name = "speaker_system.deleted"


@outgoing
class SpeakerChanged(BaseObjectChanged):
    name = "speaker.changed"


@outgoing
class SpeakerAdded(BaseObjectAdded):
    name = "speaker.added"


@outgoing
class SpeakerDeleted(BaseObjectDeleted):
    name = "speaker.deleted"
