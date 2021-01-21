from abc import ABC

from pydantic.main import BaseModel
from django.utils.translation import gettext as _

from voteit.messaging.abcs import DeferredJob, BaseIncomingMessage, ContextAction
from voteit.messaging.messages.text import TextResponse
from voteit.speaker.models import SpeakerList
from voteit.speaker.permissions import SpeakerListPermissions


class SpeakerActionSchema(BaseModel):
    pk: int  # which list to perform the action on


# FIXME: Moderator actions
# FIXME: Proper tests
class ModeratorSpeakerActionSchema(SpeakerActionSchema):
    userid: int  # Moderators may do actions for someone else


class _ListMessage(BaseIncomingMessage, DeferredJob, ContextAction, ABC):
    model = SpeakerList
    schema = SpeakerActionSchema
    data: SpeakerActionSchema


class SpeakerListEnter(_ListMessage):
    name = "speaker_list.enter"
    permission = SpeakerListPermissions.ENTER

    def run_job(self):
        self.assert_perm()
        existing_obj = self.context.speakers.filter(user=self.user).first()
        if existing_obj is not None:
            msg = TextResponse.from_message(self, msg=_("Already in list"))
        else:
            self.context.speaker_items.create(user=self.user)
            msg = TextResponse.from_message(self, msg=_("Added"))
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


class SpeakerListLeave(_ListMessage):
    name = "speaker_list.leave"
    permission = SpeakerListPermissions.LEAVE

    def run_job(self):
        self.assert_perm()
        existing_obj = self.context.speakers.filter(user=self.user).first()
        if existing_obj is not None:
            existing_obj.delete()
            msg = TextResponse.from_message(self, msg=_("Removed from list"))
        else:
            msg = TextResponse.from_message(self, msg=_("Not in list"))
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg
