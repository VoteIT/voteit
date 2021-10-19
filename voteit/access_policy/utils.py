from __future__ import annotations

from datetime import timedelta
from logging import getLogger
from typing import List
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils.timezone import now

from voteit.core.workflows import SendWf
from voteit.meeting.models import Meeting

if TYPE_CHECKING:
    from voteit.core.models import User
    from voteit.core.component import Registry
    from voteit.access_policy.registries import InviteDataRegistry
    from voteit.access_policy.messages import SendInvitesSchema
    from voteit.access_policy.models import AccessPolicy
    from voteit.access_policy.models import InviteDispatch
    from voteit.access_policy.models import MeetingInvite

logger = getLogger(__name__)


def get_policies(meeting: Meeting, only_active=True) -> List[AccessPolicy]:
    """
    Return meeting access policies
    """
    query = {"meeting": meeting}
    if only_active:
        query["active"] = True
    results = []

    reg = get_access_policy_registry()
    for ap_klass in reg.values():
        ap = ap_klass.objects.filter(**query).first()
        if ap is not None:
            results.append(ap)
    return results
    # return [ap for ap_class in reg.values() if ap := ap_class.objects.filter(**query).first()]


def get_access_policy_registry() -> Registry:
    from .registries import access_policies

    return access_policies


def get_invite_data_registry() -> InviteDataRegistry:
    from .registries import invite_data

    return invite_data


def get_dispatchers_registry() -> Registry:
    from .registries import invite_dispatchers

    return invite_dispatchers


def create_dispatch_and_schedule_invites(
    created_by: User = None, **kwargs
) -> InviteDispatch:
    from voteit.access_policy.messages import SendInvitesSchema

    send_data = SendInvitesSchema(**kwargs)
    meeting: Meeting = Meeting.objects.get(pk=send_data.meeting)
    send_exclude_ts = now() - timedelta(hours=send_data.resend_minimum)
    invites_qs = meeting.invites.filter(send_state__in=send_data.states).exclude(
        last_sent__gt=send_exclude_ts
    )
    with transaction.atomic(durable=True):
        invite_dispatch: InviteDispatch = meeting.invite_dispatches.create(
            subject=send_data.subject,
            body=send_data.body,
            dispatcher_name=send_data.dispatcher_name,
            created_by=created_by,
        )
        invite_dispatch.invites.set(invites_qs)
        invites_qs.update(send_state=SendWf.SCHEDULED)
    return invite_dispatch
