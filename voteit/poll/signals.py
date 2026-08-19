from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from django.contrib.auth.models import AbstractUser
from django.db import IntegrityError
from django.db import models
from django.db import transaction
from django.db.models.signals import m2m_changed
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import Signal
from django.dispatch import receiver
from voteit.core.signals import after_sm_transition
from voteit.messaging.channels import UserChannel
from voteit.messaging.signals import channel_subscribed
from sql_util.aggregates import SubqueryCount

from voteit.agenda.models import AgendaItem
from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import on_transaction_commit
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.poll.jobs import schedule_poll_status_publish
from voteit.poll.messages import ElectoralRegisterChanged
from voteit.poll.messages import ElectoralRegisterDeleted
from voteit.poll.messages import GenericVoteResponse
from voteit.poll.messages import PollChanged
from voteit.poll.messages import PollDeleted
from voteit.poll.messages import PollStatus
from voteit.poll.messages import VoteTransferChanged
from voteit.poll.messages import VoteTransferDeleted
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.poll.models import Vote
from voteit.poll.models import VoteTransfer
from voteit.poll.rest_api.serializers import ElectoralRegisterSerializer
from voteit.poll.rest_api.serializers import PollDetailSerializer
from voteit.poll.rest_api.serializers import VoteSerializer
from voteit.poll.rest_api.serializers import VoteTransferSerializer

if TYPE_CHECKING:
    from voteit.messaging.state import AppState
    from voteit.proposal.models import Proposal

logger = getLogger(__name__)


# Sent after voter weight has been updated!
# arguments:
#   instance: The electoral register
new_er_created = Signal()


@receiver(channel_subscribed, sender=MeetingChannel)
def send_ongoing_meeting_poll_stats(context: Meeting, app_state: AppState, **kw):
    """
    Populate app_state with current poll status
    """
    payloads = []
    for poll in (
        context.polls.filter(state="ongoing")
        .annotate(voted=SubqueryCount("votes"))
        .select_related("electoral_register")
    ):
        total = (
            len(poll.electoral_register.voter_data) if poll.electoral_register else 0
        )
        payloads.append({"pk": poll.pk, "voted": poll.voted, "total": total})
    app_state.add_batch(PollStatus, payloads)


@receiver(channel_subscribed, sender=ParticipantsChannel)
def participants_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    """
    Populate app_state with current meeting polls, except private ones
    """
    qs = (
        context.polls.exclude(state="private")
        .exclude(agenda_item__state=AgendaItemStateMachine.private.value)
        .prefetch_related("proposals")
    )
    serializer = PollDetailSerializer(qs, many=True)
    if serializer.data:
        app_state.add_batch(PollChanged, serializer.data)


@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_subscribed(context: Meeting, app_state: AppState, user: AbstractUser, **kw):
    # FIXME: Transmitting all vote data is probably not a good idea for large meetings.
    # Perhaps change this?
    # We're sending all votes, it is the users own data so private AI shouldn't matter here.
    vote_qs = Vote.objects.filter(
        poll__in=context.polls.all(), user=user
    ).prefetch_related("poll")
    vote_serializer = VoteSerializer(vote_qs, many=True)
    for item in vote_serializer.data:
        app_state.append(GenericVoteResponse(payload=item))
    if context.latest_er:
        app_state.append(
            ElectoralRegisterChanged(
                payload=ElectoralRegisterSerializer(context.latest_er).data
            )
        )
    if context.vote_transfer_policy is not None:
        vt_serializer = VoteTransferSerializer(context.vote_transfers.all(), many=True)
        if vt_serializer.data:
            app_state.add_batch(VoteTransferChanged, vt_serializer.data)


@receiver(channel_subscribed, sender=ModeratorsChannel)
def moderators_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    """
    Populate app_state with current meeting polls
    """
    serializer = PollDetailSerializer(
        context.polls.all().prefetch_related("proposals"),
        many=True,
        context={"show_withheld": True},
    )
    if serializer.data:
        app_state.add_batch(PollChanged, serializer.data)


@receiver(post_save, sender=Poll)
@disable_on_raw_save
@on_transaction_commit
def poll_change(*, instance: Poll, created: bool, **kw):
    """
    Note: This message won't work properly if django admin is used for instance.
    Proposals won't be attached unless it's during a transaction.
    We have the option to add @ensure_atomic here, but that would break all ability to change polls
    outside a transaction.
    """
    if instance.meeting is not None:
        if instance.withheld_result:
            mod_data = PollDetailSerializer(
                instance, context={"show_withheld": True}
            ).data
            part_data = PollDetailSerializer(instance).data
        else:
            mod_data = part_data = PollDetailSerializer(instance).data
        participants_ch = ParticipantsChannel.from_instance(instance.meeting)
        moderators_ch = ModeratorsChannel.from_instance(instance.meeting)
        if created:
            mod_msg = PollChanged(payload=mod_data)
            part_msg = PollChanged(payload=part_data)
        else:
            mod_msg = PollChanged(payload=mod_data)
            part_msg = PollChanged(payload=part_data)
        if instance.is_private:
            # Only care about transmitting to participants if it existed previously
            if not created:
                participants_msg = PollDeleted(payload={"pk": instance.pk})
                participants_ch.sync_publish(participants_msg, on_commit=False)
        elif instance.agenda_item is None or not instance.agenda_item.is_private:
            # Publish if ai isn't private
            participants_ch.sync_publish(part_msg, on_commit=False)
        moderators_ch.sync_publish(mod_msg, on_commit=False)


@receiver(pre_delete, sender=Poll)
def poll_delete(*, instance: Poll, **kw):
    """Poll deleted is only sent to moderators if the poll's private"""
    if instance.meeting is not None:
        moderators_ch = ModeratorsChannel.from_instance(instance.meeting)
        msg = PollDeleted(payload={"pk": instance.pk})
        moderators_ch.sync_publish(msg)
        # Publish to participants if poll isn't private. If agenda item exists, make sure it's not private
        if not instance.is_private:
            if instance.agenda_item is None or not instance.agenda_item.is_private:
                participants_ch = ParticipantsChannel.from_instance(instance.meeting)
                participants_ch.sync_publish(msg)


@receiver(after_sm_transition, sender=AgendaItem)
def private_ai_published(instance: AgendaItem, source, target, event, **kw):
    """
    Notify participants of any existing polls
    Note that polls may appear before the agenda item does!
    """
    if (
        source.value == AgendaItemStateMachine.private.value
        and instance.meeting is not None
    ):
        participants_ch = ParticipantsChannel.from_instance(instance.meeting)
        for poll in instance.polls.exclude(state="private"):
            data = PollDetailSerializer(poll).data
            msg = PollChanged(payload=data)
            participants_ch.sync_publish(msg)


@receiver(new_er_created)
def push_new_er(instance: ElectoralRegister, **kwargs):
    """
    Special signals for ER since they have M2M relations that are updated after post_save signal is sent.
    """
    meeting_ch = MeetingChannel(instance.meeting_id)
    data = ElectoralRegisterSerializer(instance).data
    msg = ElectoralRegisterChanged(payload=data)
    meeting_ch.sync_publish(msg)


@receiver(pre_delete, sender=ElectoralRegister)
@disable_on_raw_save
def er_deleted(*, instance: ElectoralRegister, **kw):
    """
    Electoral registers usually aren't deleted, but there are some special cases mostly for demo meetings.
    """
    if instance.meeting_id is not None:
        # We can't really do anything if it is!
        meeting_ch = MeetingChannel(instance.meeting_id)
        msg = ElectoralRegisterDeleted(payload={"pk": instance.pk})
        meeting_ch.sync_publish(msg)


@receiver(m2m_changed, sender=Poll.proposals.through)
def validate_related_proposals(
    instance: Poll | Proposal, action, pk_set, reverse, **kw
):
    if action == "pre_add":
        if reverse:
            instance: Proposal
            same_meeting_poll_pks = set(
                Poll.objects.filter(
                    meeting=instance.meeting, pk__in=pk_set
                ).values_list("pk", flat=True)
            )
            alien_poll_pks = pk_set - same_meeting_poll_pks
            if alien_poll_pks:
                raise IntegrityError(
                    f"Polls with pk {alien_poll_pks} aren't part of the same meeting"
                )
        else:
            from voteit.proposal.models import Proposal

            instance: Poll
            same_meeting_prop_pks = set(
                Proposal.objects.filter(
                    agenda_item__meeting=instance.meeting, pk__in=pk_set
                ).values_list("pk", flat=True)
            )
            alien_prop_pks = pk_set - same_meeting_prop_pks
            if alien_prop_pks:
                raise IntegrityError(
                    f"Proposals with pk {alien_prop_pks} aren't part of the same meeting"
                )


@receiver(post_save, sender=Vote)
@disable_on_raw_save
def vote_added(instance: Vote, *, created: bool, **kw):
    # We don't have to count updated votes!
    if created:
        poll = instance.poll
        if poll.meeting_id is not None:
            transaction.on_commit(
                lambda poll_pk=poll.pk: schedule_poll_status_publish(poll_pk)
            )
    # We need to send the vote to the user too, so they have access to their own data in case they're using several tabs
    user_ch = UserChannel.from_instance(instance.user)
    serializer = VoteSerializer(instance)
    msg = GenericVoteResponse(payload=serializer.data)
    user_ch.sync_publish(msg)


@receiver(pre_delete, sender=MeetingRoles)
def remove_vote_transfers(instance: MeetingRoles, **kwargs):
    """
    User was removed from meeting, so transfer can't exist.
    """
    VoteTransfer.objects.filter(meeting=instance.context).filter(
        models.Q(target=instance.user) | models.Q(source=instance.user)
    ).delete()


@receiver(post_save, sender=VoteTransfer)
@disable_on_raw_save
def send_vote_transfer(instance: VoteTransfer, *, created, **kwargs):
    serializer = VoteTransferSerializer(instance)
    if created:
        msg = VoteTransferChanged(payload=serializer.data)
    else:
        msg = VoteTransferChanged(payload=serializer.data)
    meeting_ch = MeetingChannel(instance.meeting_id)
    meeting_ch.sync_publish(msg)


@receiver(pre_delete, sender=VoteTransfer)
def send_vote_transfer_deleted(instance: VoteTransfer, **kwargs):
    meeting_ch = MeetingChannel(instance.meeting_id)
    msg = VoteTransferDeleted(payload={"pk": instance.pk})
    meeting_ch.sync_publish(msg)
