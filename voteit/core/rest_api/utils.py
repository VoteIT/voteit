""" REST-specific utils"""

from __future__ import annotations

import logging
from typing import Callable
from typing import Generator
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext as _
from oauthlib.oauth2 import InvalidGrantError
from requests.exceptions import ConnectionError as RConnectionError
from requests.exceptions import JSONDecodeError
from rest_framework.exceptions import APIException
from rest_framework.exceptions import NotAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError

from voteit.core.permissions import NOT_ALLOWED

if TYPE_CHECKING:
    from pydantic import ValidationError as PydanticValidationError
    from django.db.models import Model
    from voteit.core.models import User
    from voteit.organisation.models import OAuth2Provider
    from voteit.organisation.models import Organisation
    from voteit.meeting.models import Meeting
    from django_fsm import Transition


def get_identity_data(user: User) -> dict:
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
    try:
        response = oauth_session.get(provider.identity_url)
    except RConnectionError:
        # Proper exception later?
        exc = APIException(
            detail=_("Identity service not available right now"),
            code="service_unavailable",
        )
        exc.status_code = 503
        raise exc
    except InvalidGrantError:
        raise NotAuthenticated(
            detail=_("You need to login again to use invites"),
        )
    # Not the correct serializer exception, but this is kind of the crash and burn...
    if not response.ok:
        try:
            err_data = response.json()
        except JSONDecodeError:
            logging.exception("Identity provider json error")
            err_data = "Unknown error while fetching invites"
        raise ValidationError(err_data)
    return response.json()


def perm_denied_msg(perm, obj):
    return _("You're missing the permission '%(perm)s' on %(obj)s.") % {
        "perm": perm,
        "obj": obj,
    }


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


def get_valid_transitions_dict(
    instance: Model,
    attr: str = "state",
) -> dict[str, Transition]:
    return {x.name: x for x in get_valid_transitions(instance, attr=attr)}


def drf_do_transition(
    *,
    instance: Model,
    transition_name,
    valid_transitions: dict,
    user: User,
    field_name: str = "state",
):
    """
    This method produces predictable exceptions when running transitions. It's meant for DRF contexts.
    """
    if transition_name is None:
        raise ValidationError(detail={"transition": [_("Transition not specified")]})
    if transition_name not in valid_transitions:
        raise ValidationError(
            detail={
                "transition": [
                    _("Invalid transition: %(name)s") % {"name": transition_name}
                ]
            }
        )
    transition = valid_transitions[transition_name]
    meta = transition.method._django_fsm
    current_state = getattr(instance, field_name)
    if not meta.has_transition(current_state):
        raise ValidationError(
            detail={
                "transition": [
                    _("Can't switch from state '%(state)s' using method '%(method)s'")
                    % {
                        "state": current_state,
                        "method": transition.method.__name__,
                    }
                ]
            }
        )
    for condition in transition.conditions:
        if not condition(instance):
            if hasattr(condition, "title"):
                msg = condition.title
            else:
                msg = _("Guard %(guard)s blocks transition %(name)s") % {
                    "name": transition_name,
                    "guard": condition.__name__,
                }
            raise ValidationError(detail={"transition": [msg]})
    if not transition.has_perm(instance, user):
        raise PermissionDenied(perm_denied_msg(transition.permission, instance))
    getattr(instance, transition_name)()


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
    raise ValidationError(_("Can't find meeting"))


def pydantic_to_drf_validation_error(error: PydanticValidationError) -> ValidationError:
    """
    >>> import pydantic
    >>> class Number(pydantic.BaseModel):
    ...     num: int
    ...
    >>> try:
    ...     Number(num='a')
    ... except pydantic.ValidationError as exc:
    ...     new_exc = pydantic_to_drf_validation_error(exc)
    >>> isinstance(new_exc, ValidationError)
    True
    >>> new_exc
    ValidationError({'num': 'value is not a valid integer'})
    """
    eoutput = {}
    for error in error.errors():
        for loc in error["loc"]:
            eoutput[loc] = error["msg"]
    return ValidationError(eoutput)
