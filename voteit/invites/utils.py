from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from voteit.invites.registries import InviteAdapterRegistry

if TYPE_CHECKING:
    ...

logger = getLogger(__name__)


def get_invite_adapter_registry() -> InviteAdapterRegistry:
    from .registries import invite_adapter_registry

    return invite_adapter_registry


# def create_dispatch_and_schedule_invites(
#     created_by: User = None, **kwargs
# ) -> InviteDispatch:
#     from voteit.invites.messages import SendInvitesSchema
#
#     send_data = SendInvitesSchema(**kwargs)
#     meeting: Meeting = Meeting.objects.get(pk=send_data.meeting)
#     send_exclude_ts = now() - timedelta(hours=send_data.resend_minimum)
#     invites_qs = meeting.invites.filter(send_state__in=send_data.states).exclude(
#         last_sent__gt=send_exclude_ts
#     )
#     with transaction.atomic(durable=True):
#         invite_dispatch: InviteDispatch = meeting.invite_dispatches.create(
#             subject=send_data.subject,
#             body=send_data.body,
#             dispatcher_name=send_data.dispatcher_name,
#             created_by=created_by,
#         )
#         invite_dispatch.invites.set(invites_qs)
#         invites_qs.update(send_state=SendWf.SCHEDULED)
#     return invite_dispatch
