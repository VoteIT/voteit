# Common validators
from typing import Dict

from django.core import validators
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from voteit.core.utils import get_model_by_shortname


def validate_model_shortname(v: str):
    """
    Make sure it's a model that exists and has roles
    >>> validate_model_shortname("meeting")
    'meeting'
    >>> validate_model_shortname("Meeting")
    'meeting'
    >>> validate_model_shortname("404")
    Traceback (most recent call last):
    ...
    ValueError:
    """

    v = v.lower()
    model = get_model_by_shortname(v)
    if model is None:
        raise ValueError(f"{v} is not a known content type")
    return v


def validate_roles_context_model(v: str) -> str:
    """
    Make sure it's a model that exists and has roles
    >>> validate_roles_context_model("meeting")
    'meeting'
    >>> validate_roles_context_model("Meeting")
    'meeting'
    >>> validate_roles_context_model("404")
    Traceback (most recent call last):
    ...
    ValueError:

    Context that can't have roles should fail too
    >>> validate_roles_context_model("proposal")
    Traceback (most recent call last):
    ...
    ValueError:
    """
    # Avioid circular import
    from voteit.core.models import RoleContextMixin

    v = v.lower()
    model = get_model_by_shortname(v)
    if model is None:
        raise ValueError(f"{v} is not a known content type")
    if not issubclass(model, RoleContextMixin):
        raise ValueError(f"{v} content can't have roles")
    return v


def root_validate_roles_and_model(cls, values: Dict):
    """
    Checking roles requires the model too
    >>> v = {"model": "meeting", "roles": ["participant"]}
    >>> res = root_validate_roles_and_model(None, v)
    >>> v == res
    True

    >>> v = {"model": "meeting", "roles": []}
    >>> root_validate_roles_and_model(None, v)
    Traceback (most recent call last):
    ...
    ValueError:

    >>> v = {"model": "meeting", "roles": ["participant", "404"]}
    >>> root_validate_roles_and_model(None, v)
    Traceback (most recent call last):
    ...
    ValueError:
    """
    model = get_model_by_shortname(values.get("model"))
    # This should already have passed validation - use validate_roles_context_model
    assert model is not None
    roles = set(values["roles"])
    if not roles:
        raise ValueError("Specify roles")
    not_valid = roles - set(model.roles_cls.valid_roles.keys())
    if not_valid:
        raise ValueError(f"Invalid roles for this context: {', '.join(not_valid)}")
    return values


@deconstructible
class UserIDValidator(validators.RegexValidator):
    regex = r"^[a-z0-9-\_]+\Z"
    message = (
        "Enter a valid username. This value may contain only a-z, "
        "numbers, and /-/_ characters."
    )
    flags = 0


def valid_userid(value: str) -> str:
    """
    Check if something is a reasonable userid. Won't check if it exists.

    >>> valid_userid('hello-world')
    'hello-world'
    >>> valid_userid('123-321_')
    '123-321_'
    >>> valid_userid('öl')
    Traceback (most recent call last):
    ...
    ValueError:
    """
    validator = UserIDValidator()
    try:
        validator(value)
    except ValidationError as exc:
        raise ValueError(exc.message)
    return value
