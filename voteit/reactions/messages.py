from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext as _
from pydantic import validator
from pydantic.main import BaseModel

from envelope.core.message import Message
from envelope.messages.common import Status
from envelope.messages.errors import BadRequestError
from envelope.messages.errors import ValidationErrorMsg
from envelope.utils import websocket_send
from voteit.core.utils import get_model_by_shortname
from voteit.core.validators import validate_model_shortname
from voteit.messaging.base import BaseAddObject
from voteit.messaging.base import BaseDeleteObject
from voteit.messaging.base import BaseObjectAction
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
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
    users: list[int]


class UserReactionResponseSchema(ReactionSchema):
    pk: int  # The reactions' pk!
    user: int
    agenda_item: int | None


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
        reactable = model.objects.get(pk=self.data.object_id)
        ai_pk = getattr(reactable, "agenda_item_id", None)
        if self.context.flag_mode:
            # Singleton, so only set a single reaction as true - check if any exist regardless of user
            if not reactable.reaction_set.filter(button=self.context).exists():
                reactable.reaction_set.create(
                    user=self.user,
                    button=self.context,
                    agenda_item_id=ai_pk,
                )
        else:
            # Normal multi-mode
            reactable.reaction_set.create(
                user=self.user,
                button=self.context,
                agenda_item_id=ai_pk,
            )
        response = Status.from_message(self)
        websocket_send(response, state=response.SUCCESS)
        return response


@incoming
class DeleteReaction(BaseDeleteObject):
    """
    This deletes users own reaction via the reactions pk
    """

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
class DeleteFlagReaction(BaseDeleteObject):
    """
    This deletes any users reaction on a flag button, if user has delete-permission on flag button.
    """

    name = "reaction.delete_flag"
    permission = ReactionPermissions.DELETE
    model = ReactionButton
    add_model = Reaction
    # relation_queryset_attribute = "reactions"
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
        # Flag mode should be checked via permission
        if not self.context.flag_mode:
            raise BadRequestError(
                msg="This message shouldn't be used for non-flag mode reaction buttons"
            )
        # Already validated
        model = get_model_by_shortname(model_shortname)
        ct = ContentType.objects.get_for_model(model)
        Reaction.objects.filter(
            button=self.context, object_id=self.data.object_id, content_type=ct
        ).delete()
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
