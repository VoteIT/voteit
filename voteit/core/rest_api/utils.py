"""REST-specific utils"""

from __future__ import annotations

from typing import Any
from typing import TYPE_CHECKING
from typing import TypeVar

from django.utils.translation import gettext as _
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.settings import api_settings
from rules.contrib.models import RulesModelMixin

from voteit.core import PERM

if TYPE_CHECKING:
    from pydantic import ValidationError as PydanticValidationError

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
    ValidationError({'num': 'Input should be a valid integer, unable to parse string as an integer'})

    Nested model errors are placed under their full field path, so they
    never overwrite sibling fields at a shallower level:

    >>> class Inner(pydantic.BaseModel):
    ...     value: int
    ...
    >>> class Outer(pydantic.BaseModel):
    ...     count: int
    ...     inner: Inner
    ...
    >>> _ = Outer.model_rebuild()
    >>> try:
    ...     Outer(count='bad', inner={'value': 'also-bad'})
    ... except pydantic.ValidationError as exc:
    ...     new_exc = pydantic_to_drf_validation_error(exc)
    >>> new_exc.detail == {'count': 'Input should be a valid integer, unable to parse string as an integer', 'inner': {'value': 'Input should be a valid integer, unable to parse string as an integer'}}
    True

    List errors preserve per-element positions as a list, padded with empty
    dicts for valid entries, so the index of each failure is unambiguous:

    >>> class OuterList(pydantic.BaseModel):
    ...     inner: list[Inner]
    ...
    >>> _ = OuterList.model_rebuild()
    >>> try:
    ...     OuterList(inner=[{'value': 1}, {'value': 'also-bad'}, {'value': 'very-bad'}])
    ... except pydantic.ValidationError as exc:
    ...     list_exc = pydantic_to_drf_validation_error(exc)
    >>> list_exc.detail == {'inner': [{}, {'value': 'Input should be a valid integer, unable to parse string as an integer'}, {'value': 'Input should be a valid integer, unable to parse string as an integer'}]}
    True

    Model validators belong to no single field, so they land under DRF's
    non-field key rather than being dropped:

    >>> class Ordered(pydantic.BaseModel):
    ...     low: int
    ...     high: int
    ...
    ...     @pydantic.model_validator(mode="after")
    ...     def check_order(self):
    ...         if self.low > self.high:
    ...             raise ValueError("low must not exceed high")
    ...         return self
    ...
    >>> try:
    ...     Ordered(low=2, high=1)
    ... except pydantic.ValidationError as exc:
    ...     root_exc = pydantic_to_drf_validation_error(exc)
    >>> root_exc.detail == {'non_field_errors': 'low must not exceed high'}
    True
    """
    eoutput = {}
    for err in error.errors():
        # A model validator raises with an empty loc -- it belongs to no single
        # field. pydantic v1 spelled that ("__root__",); dropping it here would
        # answer an invalid request with a bare 400 and no explanation at all.
        loc = err["loc"] or (api_settings.NON_FIELD_ERRORS_KEY,)
        _nested_set(eoutput, loc, _clean_msg(err["msg"]))
    return ValidationError(eoutput)


def _clean_msg(msg: str) -> str:
    """Strip pydantic v2's "Value error, " prefix.

    v2 prefixes the message of any ValueError raised inside a validator. These
    messages are shown to end users, and the validators already word them as
    complete sentences, so the prefix is noise.

    >>> _clean_msg("Value error, Groups are needed")
    'Groups are needed'
    >>> _clean_msg("Input should be a valid integer")
    'Input should be a valid integer'
    """
    for prefix in ("Value error, ", "Assertion failed, "):
        if msg.startswith(prefix):
            return msg[len(prefix) :]
    return msg
