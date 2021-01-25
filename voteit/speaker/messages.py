from abc import ABC

from django.contrib.auth import get_user_model
from pydantic.main import BaseModel
from django.utils.translation import gettext as _
from typing import List, Optional

from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.abcs import ContextAction
from voteit.messaging.abcs import DeferredJob
from voteit.messaging.errors import NotFoundError
from voteit.messaging.messages.text import TextResponse
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.speaker.models import SpeakerList
from voteit.speaker.permissions import SpeakerListPermissions


User = get_user_model()


class SpeakerActionSchema(BaseModel):
    pk: int  # which list to perform the action on


class _ListMessage(BaseIncomingMessage, DeferredJob, ContextAction, ABC):
    model = SpeakerList
    schema = SpeakerActionSchema
    data: SpeakerActionSchema


@incoming
class SpeakerListEnter(_ListMessage):
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
class SpeakerListLeave(_ListMessage):
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


class ModeratorSpeakerActionSchema(SpeakerActionSchema):
    userid: int  # Moderators may do actions for someone else


class _ModeratorListMessage(BaseIncomingMessage, DeferredJob, ContextAction, ABC):
    model = SpeakerList
    schema = ModeratorSpeakerActionSchema
    data: ModeratorSpeakerActionSchema

    def get_user(self):
        try:
            return User.objects.get(pk=self.data.userid)
        except User.DoesNotExist:
            raise NotFoundError.from_message(
                self, msg=_("User with pk %(pk)s") % {"pk": self.data.pk}
            )


@incoming
class ModeratorSpeakerListEnter(_ModeratorListMessage):
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
class ModeratorSpeakerListLeave(_ModeratorListMessage):
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
    agenda_item: int  # pk


class SpeakerListAdded(BaseOutgoingMessage):
    name = "speaker_list.added"
    schema = SpeakerListSchema
    data: SpeakerListSchema


class SpeakerListChanged(BaseOutgoingMessage):
    name = "speaker_list.changed"
    schema = SpeakerListSchema
    data: SpeakerListSchema
