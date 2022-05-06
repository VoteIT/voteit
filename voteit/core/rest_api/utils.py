""" REST-specific utils"""
from __future__ import annotations

from typing import Callable
from typing import Dict
from typing import Generator
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from rest_framework.exceptions import ValidationError

from voteit.core.permissions import NOT_ALLOWED

if TYPE_CHECKING:
    from voteit.core.models import User
    from voteit.organisation.models import OAuth2Provider
    from voteit.organisation.models import Organisation
    from voteit.meeting.models import Meeting
    from django_fsm import Transition


def get_identity_data(user: User) -> Dict:
    """
    Returns users identity data from identity server
    """

    try:
        organisation: Organisation = user.organisation
    except AttributeError:
        raise ValidationError(
            "Your user isn't attached to an organisation so login this way will never work"
        )
    try:
        provider: OAuth2Provider = organisation.provider
    except AttributeError:
        raise ValidationError(
            "The organisation you belong to has no login provider, so login will never work"
        )
    oauth_session = user.oauth_session()
    response = oauth_session.get(provider.identity_url)
    # Not the correct serializer exception, but this is kind of the crash and burn...
    # FIXME: Cases to handle: Token expired, user not found etc
    response.raise_for_status()
    return response.json()


def get_valid_transitions(
    instance,
    attr="state",
) -> Generator[Transition]:
    """
    Return all transitions that make any sense to test from a specific state.

    The reason for duplicating this functionality from FSM is that we'll want to conduct the tests one by one
    to give the user meaningfull feedback.

    Required user checks are permission and condition.
    """
    descriptor = getattr(instance.__class__, attr)
    field = descriptor.field
    curr_state = field.get_state(instance)
    transitions = field.transitions[instance.__class__]
    for transition in transitions.values():
        # This is the decorated method on the model, not the transition object!
        transition: Callable
        meta = transition._django_fsm
        if valid_transition := meta.has_transition(curr_state) and meta.get_transition(
            curr_state
        ):
            valid_transition: Transition
            # Is this a hidden transition?
            if valid_transition.permission != NOT_ALLOWED:
                yield valid_transition


def _pos_int_or_validation_error(value) -> int:
    """
    >>> _pos_int_or_validation_error("1")
    1
    >>> _pos_int_or_validation_error("0")
    Traceback (most recent call last):
    ...
    rest_framework.exceptions.ValidationError:
    >>> _pos_int_or_validation_error("-1")
    Traceback (most recent call last):
    ...
    rest_framework.exceptions.ValidationError:
    >>> _pos_int_or_validation_error("a")
    Traceback (most recent call last):
    ...
    rest_framework.exceptions.ValidationError:
    """
    try:
        value = int(value)
    except (ValueError, TypeError):
        raise ValidationError("Invalid")
    if value > 0:
        return value
    raise ValidationError("Invalid")


def meeting_from_unsafe_data(serializer) -> Meeting:
    """
    This method should only be used directly by a serializer validation method
    """
    # Via agenda_item
    ai_query_val = serializer.initial_data.get("agenda_item", None)
    if ai_query_val:
        ai_query_val = _pos_int_or_validation_error(ai_query_val)
        from voteit.agenda.models import AgendaItem

        try:
            ai = AgendaItem.objects.get(pk=ai_query_val)
            if ai.meeting:
                return ai.meeting
        except ObjectDoesNotExist:
            pass
    # Via meeting
    meeting_query_val = serializer.initial_data.get("meeting", None)
    if meeting_query_val:
        meeting_query_val = _pos_int_or_validation_error(meeting_query_val)
        from voteit.meeting.models import Meeting

        try:
            return Meeting.objects.get(pk=meeting_query_val)
        except ObjectDoesNotExist:
            pass
    # Fail
    raise ValidationError("Can't find meeting")
