# Common validators
from collections.abc import Iterable
from typing import Dict

from django.core import validators
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _

from voteit.core.utils import get_model_by_shortname


@deconstructible
class ImageValidator:
    def __init__(
        self,
        max_size: int = 300_00,
        allowed_mimes=("image/jpeg", "image/png", "image/webp"),
    ):
        self.max_size = max_size
        self.allowed_mimes = allowed_mimes

    def __call__(self, file):
        try:
            import magic  # requires libmagic system library
        except ImportError:
            raise ValidationError(_("Image upload is currently unavailable."))

        if file.size > self.max_size:
            raise ValidationError(_("File too large. Max size: %d" % self.max_size))
        file.seek(0)
        data = file.read(2048)
        file.seek(0)
        try:
            mime = magic.from_buffer(data, mime=True)
        except Exception:
            raise ValidationError(_("Image upload is currently unavailable."))
        # Some libmagic builds cannot identify RIFF sub-types (WebP) from a buffer;
        # fall back to manual signature check in that case.
        if mime == "application/octet-stream" and len(data) >= 12:
            if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                mime = "image/webp"
        if mime not in self.allowed_mimes:
            raise ValidationError(
                _("Unsupported file type, must be one of: %s.")
                % ", ".join(self.allowed_mimes)
            )


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
    >>> from voteit.meeting.roles import ROLE_PARTICIPANT
    >>> v = {"model": "meeting", "roles": [ROLE_PARTICIPANT]}
    >>> res = root_validate_roles_and_model(None, v)
    >>> v == res
    True

    >>> v = {"model": "meeting", "roles": []}
    >>> root_validate_roles_and_model(None, v)
    Traceback (most recent call last):
    ...
    ValueError:

    >>> v = {"model": "meeting", "roles": ["p4"]}
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
    not_valid = roles - set(model.roles_cls.valid_roles)
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


@deconstructible
class TagValidator(validators.RegexValidator):
    r"""
    This should cause errors on anything that we really don't under any circumstances want to allow,
    including failing legacy data.

    >>> f = lambda x: TagValidator().regex.search(x) is not None  # Instead of exceptions here
    >>> f('HelloWorld.')
    True
    >>> f('HelloWorld.123')
    True
    >>> f('Hellö_wörld')
    True
    >>> f('你好')
    True
    >>> f("helloworld"*5)
    True
    >>> f("helloworld"*10) # too long
    False
    >>> f('hi')
    True
    >>> f('h')
    False
    >>> f('Hello#World.')
    False
    >>> f('Hello World')
    False
    >>> f("Hello\nWorld")
    False
    >>> f("§Hello-World")
    False
    """

    regex = r"^[\w\\.\-]{2,50}$"
    message = (
        "Tags must be 2-50 characters long and only contain letters, numbers and .-_"
    )


tag_validator = TagValidator()


def get_invalid_tags(tags: Iterable[str]) -> set[str]:
    bad = set()
    for tag in tags:
        try:
            tag_validator(tag)
        except ValidationError:
            bad.add(tag)
    return bad


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
