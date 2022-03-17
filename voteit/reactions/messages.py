from __future__ import annotations
from typing import Optional

from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext as _
from pydantic import validator
from pydantic.main import BaseModel
from typing import List

from envelope.core.message import Message
from envelope.messages.common import Status
from envelope.messages.errors import ValidationErrorMsg
from envelope.utils import websocket_send
from voteit.core.utils import get_model_by_shortname
from voteit.core.validators import validate_model_shortname
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.messaging.messages.base import BaseAddObject
from voteit.messaging.messages.base import BaseDeleteObject
from voteit.messaging.messages.base import BaseObjectAction
from voteit.messaging.messages.base import BaseObjectAdded
from voteit.messaging.messages.base import BaseObjectChanged
from voteit.messaging.messages.base import BaseObjectDeleted
from voteit.reactions.models import Reaction
from voteit.reactions.models import ReactionButton
from voteit.reactions.permissions import ReactionButtonPermissions
from voteit.reactions.permissions import ReactionPermissions


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
    content_type: str
    object_id: int
    button: int

    _validate_content_type = validator("content_type", allow_reuse=True)(
        validate_model_shortname
    )


class ReactionCountSchema(ReactionSchema):
    count: int


class ReactionUserListSchema(ReactionSchema):
    users: List[int]


class UserReactionResponseSchema(ReactionSchema):
    pk: int  # The reactions pk!
    user: int
    agenda_item: Optional[int]


@outgoing
class ReactionCount(Message):
    name = "reaction.count"
    schema = ReactionCountSchema
    data: ReactionCountSchema


@outgoing
class UserReactionAdded(Message):
    """
    Normally only sent to the user who added it!
    """

    name = "reaction.added"
    schema = UserReactionResponseSchema
    data: UserReactionResponseSchema


@outgoing
class UserReactionDeleted(BaseObjectDeleted):
    name = "reaction.deleted"


@incoming
class AddReaction(BaseAddObject):
    name = "reaction.add"
    permission = ReactionPermissions.ADD
    model = ReactionButton  # This is the context for the action!
    add_model = Reaction
    relation_queryset_attribute = "reactions"
    schema = ReactionSchema
    data: ReactionSchema
    context: ReactionButton
    context_schema_attr = "button"

    def run_job(self) -> Status:
        self.assert_perm()
        model_shortname = self.data.content_type
        if model_shortname not in self.context.allowed_models:
            raise ValidationErrorMsg.from_message(
                self,
                msg=_("This type of reaction can't be added to this content type"),
                errors=[
                    {"loc": ("content_type",), "msg": "Invalid", "type": "value.error"}
                ],
            )
        # Already validated
        model = get_model_by_shortname(model_shortname)
        ct = ContentType.objects.get_for_model(model)
        reactable = model.objects.get(pk=self.data.object_id)
        ai = getattr(reactable, "agenda_item", None)
        # FIXME: set object directly? Reverse relation doesn't seem to work now
        Reaction.objects.get_or_create(
            user=self.user,
            button=self.context,
            object_id=reactable.id,
            agenda_item=ai,
            content_type=ct,
        )
        response = Status.from_message(self)
        websocket_send(response, state=response.SUCCESS)
        return response


@incoming
class DeleteReaction(BaseDeleteObject):
    name = "reaction.delete"
    permission = ReactionPermissions.DELETE
    model = Reaction

    def run_job(self) -> Status:
        self.assert_perm()
        self.context.delete()
        response = Status.from_message(self)
        websocket_send(response, state=response.SUCCESS)
        return response


@incoming
class ListReactionUsers(BaseObjectAction):
    name = "reaction.list"
    permission = ReactionButtonPermissions.LIST_REACTIONS
    model = ReactionButton  # This is the context for the action!
    schema = ReactionSchema
    data: ReactionSchema
    context: ReactionButton
    context_schema_attr = "button"

    def run_job(self) -> ReactionUserListResponse:
        self.assert_perm()
        model_shortname = self.data.content_type
        # Already validated
        model = get_model_by_shortname(model_shortname)
        ct = ContentType.objects.get_for_model(model)
        user_pks = self.context.reactions.filter(
            object_id=self.data.object_id, content_type=ct
        ).values_list("user", flat=True)
        response = ReactionUserListResponse.from_message(
            self, users=list(user_pks), **self.data.dict()
        )
        websocket_send(response, state=response.SUCCESS)
        return response


@outgoing
class ReactionUserListResponse(Message):

    name = "reaction.list"
    schema = ReactionUserListSchema
    data: ReactionUserListSchema
