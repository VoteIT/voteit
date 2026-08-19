"""REST-specific utils"""

from __future__ import annotations

from typing import Any
from typing import TYPE_CHECKING
from typing import TypeVar

from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext as _
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rules.contrib.models import RulesModelMixin

from voteit.core import PERM

if TYPE_CHECKING:
    from pydantic import ValidationError as PydanticValidationError
    from voteit.meeting.models import Meeting

T = TypeVar("T", bound=RulesModelMixin)


def perm_denied_msg(perm, obj):
    return _("You're missing the permission '%(perm)s' on %(obj)s.") % {
        "perm": perm,
        "obj": obj,
    }


def validate_model_add(serializer, model: T | type[T], context: Any = None) -> None:
    user = serializer.context["request"].user
    model_perm = model.get_perm(PERM.ADD)
    if not user.has_perm(model_perm, context):
        raise PermissionDenied(perm_denied_msg(model_perm, context))


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

    >>> from rest_framework.serializers import Serializer
    >>> from voteit.meeting.models import Meeting
    >>> m = Meeting()
    >>> serializer = Serializer(data={}, context={'meeting': m})
    >>> m is meeting_from_unsafe_data(serializer)
    True
    """
    # Via context is a lot better
    from voteit.meeting.models import Meeting

    _meeting = serializer.context.get("meeting")
    if isinstance(_meeting, Meeting):
        return _meeting

    # Via agenda_item
    many = serializer.initial_data and isinstance(serializer.initial_data, list)
    if many:
        # Just make one attempt here
        ai_query_val = serializer.initial_data[0].get("agenda_item", None)
    else:
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
    if many:
        meeting_query_val = serializer.initial_data[0].get("meeting", None)
    else:
        meeting_query_val = serializer.initial_data.get("meeting", None)
    if meeting_query_val:
        meeting_query_val = _pos_int_or_validation_error(meeting_query_val)
        try:
            return Meeting.objects.get(pk=meeting_query_val)
        except ObjectDoesNotExist:
            pass
    # Fail
    raise ValidationError(_("Can't find meeting"))


def _nested_set(container, path, value):
    """Insert value into a nested dict/list structure, creating nodes as needed.

    Integer path segments indicate list positions; string segments indicate dict keys.
    Lists are padded with empty dicts when the index exceeds the current length.
    """
    key = path[0]
    if len(path) == 1:
        if isinstance(container, list):
            while len(container) <= key:
                container.append({})
            container[key] = value
        else:
            container[key] = value
        return
    next_key = path[1]
    child_type = list if isinstance(next_key, int) else dict
    if isinstance(container, list):
        while len(container) <= key:
            container.append(child_type())
        if not isinstance(container[key], child_type):
            container[key] = child_type()
    else:
        if key not in container or not isinstance(container[key], child_type):
            container[key] = child_type()
    _nested_set(container[key], path[1:], value)


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

    Nested model errors are placed under their full field path, so they
    never overwrite sibling fields at a shallower level:

    >>> class Inner(pydantic.BaseModel):
    ...     value: int
    ...
    >>> class Outer(pydantic.BaseModel):
    ...     count: int
    ...     inner: Inner
    ...
    >>> Outer.model_rebuild()
    >>> try:
    ...     Outer(count='bad', inner={'value': 'also-bad'})
    ... except pydantic.ValidationError as exc:
    ...     new_exc = pydantic_to_drf_validation_error(exc)
    >>> new_exc.detail == {'count': 'value is not a valid integer', 'inner': {'value': 'value is not a valid integer'}}
    True

    List errors preserve per-element positions as a list, padded with empty
    dicts for valid entries, so the index of each failure is unambiguous:

    >>> class OuterList(pydantic.BaseModel):
    ...     inner: list[Inner]
    ...
    >>> OuterList.model_rebuild()
    >>> try:
    ...     OuterList(inner=[{'value': 1}, {'value': 'also-bad'}, {'value': 'very-bad'}])
    ... except pydantic.ValidationError as exc:
    ...     list_exc = pydantic_to_drf_validation_error(exc)
    >>> list_exc.detail == {'inner': [{}, {'value': 'value is not a valid integer'}, {'value': 'value is not a valid integer'}]}
    True
    """
    eoutput = {}
    for err in error.errors():
        loc = err["loc"]
        if loc:
            _nested_set(eoutput, loc, err["msg"])
    return ValidationError(eoutput)
