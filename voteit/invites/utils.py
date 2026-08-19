from __future__ import annotations

import json
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
    meeting: Meeting, queryset: models.QuerySet[MeetingInvite], annotate: bool = False
):
    """
    Publish MeetingInviteChanged for each invite in queryset.
    Pass annotate=True when calling after run_annotations so that has_annotations
    is read from the queryset annotation rather than a live DB fetch.
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
        msg = MeetingInviteChanged(payload=data)
        ch.sync_publish(msg)


def _mask_email(value: str) -> str:
    if "@" in value:
        parts = value.split("@")

        return "@".join(f"*{x[int(len(x) / 2) :]}" for x in parts)
    return value


def _mask_swedish_ssn(value: str) -> str:
    return f"{value[0:6]}*"


_DICT_MASKERS = {
    "email": _mask_email,
    "swedish_ssn": _mask_swedish_ssn,
}


def user_data_mask(value: str) -> str:
    """
    >>> user_data_mask('{"email":"someone@betahaus.net", "swedish_ssn":"121212-1212", "otherstuff": "HelloWorld"}')
    '{"email": "*eone@*us.net", "swedish_ssn": "121212*", "otherstuff": "HelloWorld"}'
    """
    if any(f'"{x}"' in value for x in _DICT_MASKERS):
        data = json.loads(value)
        for k, func in _DICT_MASKERS.items():
            if k in data:
                data[k] = func(data[k])
        return json.dumps(data)
    return value
