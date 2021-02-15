from typing import Optional, Union

from django.contrib.contenttypes.models import ContentType
from pydantic import validator
from pydantic.main import BaseModel
from django.utils.translation import gettext as _

from voteit.messaging.abcs import (
    BaseOutgoingMessage,
    BaseIncomingMessage,
    DeferredJob,
    ContextAction,
)
from voteit.messaging.decorators import outgoing, incoming
from voteit.messaging.messages.base import (
    BaseObjectAdded,
    BaseObjectChanged,
    BaseObjectDeleted,
    BaseDeleteObject,
)
from voteit.messaging.messages.text import TextResponse
from voteit.reactions.models import Reaction, ReactionButton
from voteit.reactions.permissions import ReactionButtonPermissions, ReactionPermissions


@outgoing
class ButtonAdded(BaseObjectAdded):
    name = "reaction_button.added"


@outgoing
class ButtonChanged(BaseObjectChanged):
    name = "reaction_button.changed"


@outgoing
class ButtonDeleted(BaseObjectDeleted):
    name = "reaction_button.deleted"


class ReactionSchema(BaseModel):
    content_type: Union[ContentType, str]
    object_id: int
    button: int

    @validator("content_type")
    def validate_content_type(cls, v):
        if isinstance(v, ContentType):
            v = ".".join(v.natural_key())
        if len(v.split(".")) != 2:
            raise ValueError(
                "content_type must be separated with a dot: app_name.content_type"
            )
        v = v.lower()
        return v

    class Config:
        arbitrary_types_allowed = True


class ReactionCountSchema(ReactionSchema):
    count: int


class UserReactionResponseSchema(ReactionSchema):
    pk: int  # The reactions pk!
    user: int
    agenda_item: Optional[int]


@outgoing
class ReactionCount(BaseOutgoingMessage):
    name = "reaction.count"
    schema = ReactionCountSchema
    data: ReactionCountSchema


@outgoing
class UserReactionAdded(BaseOutgoingMessage):
    """ Normally only sent to the user who added it!"""

    name = "reaction.added"
    schema = UserReactionResponseSchema
    data: UserReactionResponseSchema


@outgoing
class UserReactionDeleted(BaseObjectDeleted):
    name = "reaction.deleted"


class AddReactionSchema(BaseModel):
    pk: int  # The buttons schema! Since this is where the permission check is done.
    content_type: str
    object_id: int

    @validator("content_type")
    def validate_content_type(cls, v):
        if len(v.split(".")) != 2:
            raise ValueError(
                "content_type must be separated with a dot: app_name.content_type"
            )
        v = v.lower()
        return v


@incoming
class AddReaction(BaseIncomingMessage, DeferredJob, ContextAction):
    schema = AddReactionSchema
    data: AddReactionSchema
    permission = ReactionPermissions.ADD
    name = "reaction.add"
    model = ReactionButton

    def run_job(self) -> TextResponse:
        self.assert_perm()
        ct_parts = self.data.content_type.split(".")
        ct = ContentType.objects.get_by_natural_key(*ct_parts)
        reactable = ct.get_object_for_this_type(pk=self.data.object_id)
        ai = getattr(reactable, "agenda_item", None)
        # FIXME: set object directly? Reverse relation doesn't seem to work now
        reaction, created = Reaction.objects.get_or_create(
            user=self.user,
            button=self.context,
            object_id=reactable.id,
            agenda_item=ai,
            content_type=ct,
        )
        response = TextResponse.from_message(self, msg="")
        response.send_outgoing(self.mm.consumer_name, success=True)
        return response


@incoming
class DeleteReaction(BaseDeleteObject):
    name = "reaction.delete"
    permission = ReactionPermissions.DELETE
    model = Reaction

    def run_job(self) -> TextResponse:
        self.assert_perm(msg=_("You're not allowed to change this now"))

        self.context.delete()
        response = TextResponse.from_message(self, msg="")
        response.send_outgoing(self.mm.consumer_name, success=True)
        return response
