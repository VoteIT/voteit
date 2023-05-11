from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from django.db import models
    from voteit.invites.models import MeetingInvite
    from voteit.meeting.models import Meeting
    from voteit.invites.registries import InviteAdapterRegistry

logger = getLogger(__name__)


def get_invite_adapter_registry() -> InviteAdapterRegistry:
    from .registries import invite_adapter_registry

    return invite_adapter_registry


def send_updated_invites(
    meeting: Meeting, queryset: models.QuerySet[MeetingInvite], annotate=False
):
    """
    Send message to meeting channel with updated invites.
    This is more of a special case since invites have an attribute called 'has_annotations'
    that has to do with other objects.
    IE, we might not know about new annotations or that they've been removed.
    """
    from voteit.invites.channels import MeetingInvitesChannel
    from voteit.invites.messages import MeetingInviteChanged
    from voteit.invites.rest_api.serializers import MeetingInviteSerializer

    reg = get_invite_adapter_registry()
    if annotate:
        queryset = reg.prep_invites_qs_for_subscribe(queryset)
    ch = MeetingInvitesChannel.from_instance(meeting)
    serializer = MeetingInviteSerializer(queryset, many=True)
    for data in serializer.data:
        msg = MeetingInviteChanged(data=data)
        ch.sync_publish(msg)
