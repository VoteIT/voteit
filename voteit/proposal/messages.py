from __future__ import annotations
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from voteit.messaging.decorators import outgoing
from voteit.messaging.messages.base import BaseObjectAdded, BaseObjectChanged, BaseObjectDeleted

User = get_user_model()


if TYPE_CHECKING:
    pass

# @websocket_incoming_messages("proposal.add")
# class AddProposal(AddObject):
#     def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
#         add_proposal.delay(
#             user_pk=consumer.user.pk,
#             consumer_name=consumer.channel_name,
#             data=self.data,
#             message_id=message_id,
#         )
#
#
# @job("default", timeout=10)
# def add_proposal(
#     user_pk: int = None,
#     consumer_name: str = "",
#     data: Dict = None,
#     message_id: str = None,
# ):
#     # FIXME - get user, check permission, create object, report success or fail
#     pass
#
#
# @websocket_incoming_messages("proposal.change")
# class ChangeProposal(ChangeObject):
#     def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
#         change_proposal.delay(
#             user_pk=consumer.user.pk,
#             consumer_name=consumer.channel_name,
#             data=self.data,
#             pk=self.pk,
#             message_id=message_id,
#         )
#
#
# @job("default", timeout=10)
# def change_proposal(
#     user_pk: int = None,
#     consumer_name: str = "",
#     data: Dict = None,
#     pk: int = None,
#     message_id: str = None,
# ):
#     # FIXME
#     pass
#
#
# @websocket_incoming_messages("proposal.delete")
# class DeleteProposal(DeleteObject):
#     def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
#         delete_proposal.delay(
#             user_pk=consumer.user.pk,
#             consumer_name=consumer.channel_name,
#             pk=self.pk,
#             message_id=message_id,
#         )
#
#
# @job("default", timeout=10)
# def delete_proposal(
#     user_pk: int = None, consumer_name: str = "", pk: int = None, message_id: str = None
# ):
#     # FIXME
#     pass

@outgoing
class ProposalAdded(BaseObjectAdded):
    name = "proposal.added"


@outgoing
class ProposalChanged(BaseObjectChanged):
    name = "proposal.changed"


@outgoing
class ProposalDeleted(BaseObjectDeleted):
    name = "proposal.deleted"
