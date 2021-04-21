from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django_fsm.signals import post_transition
from voteit.agenda.models import AgendaItem
from voteit.agenda.workflows import AgendaItemWf
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.models import Meeting
from voteit.messaging.messages.app_state import AppState
from voteit.messaging.signals import channel_subscribed
from voteit.poll.channels import PollChannel
from voteit.poll.messages import GenericVoteResponse
from voteit.poll.messages import PollAdded
from voteit.poll.messages import PollChanged
from voteit.poll.messages import PollDeleted
from voteit.poll.messages import PollStatus
from voteit.poll.models import Poll
from voteit.poll.models import Vote
from voteit.poll.rest_api.serializers import PollDetailSerializer
from voteit.poll.rest_api.serializers import VoteSerializer
from voteit.poll.workflows import PollWf


@receiver(channel_subscribed, sender=PollChannel)
def poll_subscribed(context: Poll, app_state: AppState, **kw):
    """ Populate app_state with current poll status """
    msg = PollStatus.create(
        pk=context.pk,
        voted=context.votes.count(),
        total=context.electoral_register.voters.count(),
    )
    app_state.append(msg)


@receiver(channel_subscribed, sender=ParticipantsChannel)
def participants_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    """ Populate app_state with current meeting polls, except private ones """
    app_state.append_from_queryset(
        context.polls.exclude(state=PollWf.PRIVATE).exclude(
            agenda_item__state=AgendaItemWf.PRIVATE
        ),
        PollDetailSerializer,
        PollAdded,
    )
    # FIXME: Transmitting all vote data is probably not a good idea for large meetings.
    # Perhaps change this?
    # We're sending all votes, it is the users own data so private ai shouldn't matter here.
    app_state.append_from_queryset(
        Vote.objects.filter(poll__in=context.polls.all(), user=user),
        VoteSerializer,
        GenericVoteResponse,
    )


@receiver(channel_subscribed, sender=ModeratorsChannel)
def moderators_subscribed(context: Meeting, app_state: AppState, **kw):
    """ Populate app_state with current meeting polls """
    app_state.append_from_queryset(context.polls.all(), PollDetailSerializer, PollAdded)


@receiver(post_save, sender=Poll)
def poll_change(instance: Poll = None, created: bool = None, **kw):
    if instance.meeting is not None:
        instance.refresh_from_db(
            fields=["result_data"]
        )  # FIXME somewhere else, preferably.
        data = PollDetailSerializer(instance).data
        participants_ch = ParticipantsChannel.from_instance(instance.meeting)
        moderators_ch = ModeratorsChannel.from_instance(instance.meeting)
        if created:
            msg = PollAdded({}, **data)
        else:
            msg = PollChanged({}, **data)
        if instance.is_private:
            # Only care about transmitting to participants if it existed previously
            if not created:
                participants_msg = PollDeleted(pk=instance.pk)
                participants_ch.publish(participants_msg)
        elif instance.agenda_item is None or not instance.agenda_item.is_private:
            # Publish if ai isn't private
            participants_ch.publish(msg)
        moderators_ch.publish(msg)


@receiver(pre_delete, sender=Poll)
def poll_delete(instance: Poll = None, **kw):
    """ Poll deleted is only sent to moderators if the poll's private"""
    if instance.meeting is not None:
        moderators_ch = ModeratorsChannel.from_instance(instance.meeting)
        msg = PollDeleted({}, pk=instance.pk)
        moderators_ch.publish(msg)
        # Publish to participants if poll isn't private. If agenda item exists, make sure it's not private
        if not instance.is_private:
            if instance.agenda_item is None or not instance.agenda_item.is_private:
                participants_ch = ParticipantsChannel.from_instance(instance.meeting)
                participants_ch.publish(msg)


@receiver(post_transition, sender=AgendaItem)
def private_ai_published(instance: AgendaItem, source: str, **kw):
    """
    Notify participants of any existing polls
    Note that polls may appear before the agenda item does!
    """
    if source == AgendaItemWf.PRIVATE and instance.meeting is not None:
        participants_ch = ParticipantsChannel.from_instance(instance.meeting)
        for poll in instance.polls.exclude(state=PollWf.PRIVATE):
            data = PollDetailSerializer(poll).data
            msg = PollAdded({}, **data)
            participants_ch.publish(msg)
