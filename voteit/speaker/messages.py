from abc import ABC

from django.contrib.auth import get_user_model
from pydantic.main import BaseModel
from django.utils.translation import gettext as _
from typing import List, Optional, Dict

from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.abcs import ContextAction
from voteit.messaging.abcs import DeferredJob
from voteit.messaging.errors import NotFoundError
from voteit.messaging.errors import ValidationErrorMsg
from voteit.messaging.messages.base import BaseObjectDeleted
from voteit.messaging.messages.text import TextResponse
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.speaker.models import SpeakerList
from voteit.speaker.permissions import SpeakerListPermissions


User = get_user_model()


class SpeakerListActionSchema(BaseModel):
    pk: int  # which list to perform the action on


class SpeakerListUserSchema(SpeakerListActionSchema):
    userid: int  # Moderators may also enter someone else.


class ListMessage(BaseIncomingMessage, DeferredJob, ContextAction, ABC):
    model = SpeakerList
    schema = SpeakerListActionSchema
    data: SpeakerListActionSchema


class ModeratorListMessage(BaseIncomingMessage, DeferredJob, ContextAction, ABC):
    model = SpeakerList
    schema = SpeakerListUserSchema
    data: SpeakerListUserSchema

    def get_user(self):
        try:
            return User.objects.get(pk=self.data.userid)
        except User.DoesNotExist:
            raise NotFoundError.from_message(
                self, msg=_("User with pk %(pk)s") % {"pk": self.data.pk}
            )


@incoming
class SpeakerListEnter(ListMessage):
    name = "speaker_list.enter"
    permission = SpeakerListPermissions.ENTER

    def run_job(self):
        self.assert_perm()
        existing_obj = self.context.speaker_items.filter(
            user=self.user, order__isnull=False
        ).first()
        if existing_obj is not None:
            msg = TextResponse.from_message(self, msg=_("Already in list"))
        else:
            self.context.speaker_items.create(user=self.user)
            msg = TextResponse.from_message(self, msg=_("Added"))
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


@incoming
class SpeakerListLeave(ListMessage):
    name = "speaker_list.leave"
    permission = SpeakerListPermissions.LEAVE

    def run_job(self):
        self.assert_perm()
        existing_obj = self.context.speaker_items.filter(
            user=self.user, order__isnull=False
        ).first()
        if existing_obj is not None:
            existing_obj.delete()
            msg = TextResponse.from_message(self, msg=_("Removed from list"))
        else:
            msg = TextResponse.from_message(self, msg=_("Not in list"))
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


@incoming
class SetActiveList(ListMessage):
    name = "speaker_list.set_active"
    permission = SpeakerListPermissions.CHANGE
    context: SpeakerList

    def run_job(self):
        self.assert_perm()
        system = self.context.list_system
        if not self.context.is_active_list:
            if system.active_list and system.active_list.current is not None:
                raise ValidationErrorMsg.from_message(
                    self,
                    msg=_("Another list has an active speaker."),
                    errors=[
                        {
                            "loc": ("pk",),
                            "msg": _("List '%s' with id %s is active")
                            % (system.active_list.title, system.active_list),
                            "type": "value.error",
                        }
                    ],
                )
            system.active_list = self.context
            system.save()
            msg = TextResponse.from_message(self, msg=_("Active list changed"))
            msg.send_outgoing(self.mm.consumer_name, success=True)
            return msg


@incoming
class StartSpeakerInList(ModeratorListMessage):
    """ Start userid. Ignore if not found or already speaking. """

    name = "speaker_list.start_user"
    permission = SpeakerListPermissions.START
    context: SpeakerList

    def run_job(self):
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
        else:
            self.context.start_speaker(speaker)
            self.context.signal_list_updated()
            msg = TextResponse.from_message(self, msg=_("Started"))
            msg.send_outgoing(self.mm.consumer_name, success=True)
            return msg


@incoming
class StopSpeakerInList(ModeratorListMessage):
    """ Stop userid. Ignore if not speaking. """

    name = "speaker_list.stop_user"
    permission = SpeakerListPermissions.STOP
    context: SpeakerList

    def run_job(self):
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
        msg = TextResponse.from_message(self, msg=_("Stopped"))
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


@incoming
class ModeratorSpeakerListEnter(ModeratorListMessage):
    name = "mod_speaker_list.enter"
    permission = SpeakerListPermissions.ENTER

    def run_job(self):
        self.assert_perm()
        user = self.get_user()
        existing_obj = self.context.speaker_items.filter(
            user=user, order__isnull=False
        ).first()
        if existing_obj is not None:
            msg = TextResponse.from_message(self, msg=_("Already in list"))
        else:
            self.context.speaker_items.create(user=user)
            msg = TextResponse.from_message(self, msg=_("Added"))
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


@incoming
class ModeratorSpeakerListLeave(ModeratorListMessage):
    name = "mod_speaker_list.leave"
    permission = SpeakerListPermissions.LEAVE

    def run_job(self):
        self.assert_perm()
        user = self.get_user()
        existing_obj = self.context.speaker_items.filter(
            user=user, order__isnull=False
        ).first()
        if existing_obj is not None:
            existing_obj.delete()
            msg = TextResponse.from_message(self, msg=_("Removed from list"))
        else:
            msg = TextResponse.from_message(self, msg=_("Not in list"))
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


class OrderSchema(BaseModel):
    pk: int  # speaker list pk
    queue: List[int]  # user pks
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
    list_system: int  # pk
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
    active: bool
    title: Optional[str]
    meeting: Optional[int]
    method_name: str
    settings: Optional[Dict]
    safe_positions: Optional[int]
    active_list: Optional[int]


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
