from __future__ import annotations
from typing import TYPE_CHECKING

from voteit.agenda.channels import AgendaItemChannel
from voteit.meeting.channels import MeetingChannel


if TYPE_CHECKING:
    from voteit.messaging.abcs import BaseOutgoingMessage
    from voteit.speaker.models import SpeakerList


def get_list_method_registry():
    from voteit.speaker.registries import list_method

    return list_method


def publish_list_msg(speaker_list: SpeakerList, msg: BaseOutgoingMessage):
    if speaker_list.is_active_list and speaker_list.meeting:
        ch = MeetingChannel.from_instance(speaker_list.meeting)
        ch.publish(msg)
    elif speaker_list.agenda_item is not None:
        ai_ch = AgendaItemChannel.from_instance(speaker_list.agenda_item)
        ai_ch.publish(msg)
