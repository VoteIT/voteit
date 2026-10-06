# Common validators
import re
from collections.abc import Iterable
from typing import Dict

from django.core import validators
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _

from voteit.core.utils import get_model_by_shortname


def _fmt_bytes(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n // 1024} KB"
    return f"{n} B"


_MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


@deconstructible
class ImageValidator:
    def __init__(
        self,
        max_size: int = 300 * 1024,
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
            raise ValidationError(
                _("File too large. Max size: %s") % _fmt_bytes(self.max_size)
            )
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
        # Browsers (e.g. mobile) often send the file as "blob" with no extension.
        # Correct the name using the detected type so upload_to can use the right ext.
        ext = _MIME_TO_EXT.get(mime)
        if ext:
            base = file.name.rsplit(".", 1)[0] if "." in file.name else file.name
            file.name = f"{base}.{ext}"


_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"
_XML_NS = "http://www.w3.org/XML/1998/namespace"
# Editor metadata that design tools leave in exported files. Nothing in them renders.
_SVG_EDITOR_NAMESPACES = frozenset(
    {
        "http://www.inkscape.org/namespaces/inkscape",
        "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "http://purl.org/dc/elements/1.1/",
        "http://creativecommons.org/ns#",
    }
)
# No script, foreignObject, a, image, use of external resources or animation
# (animate/set can rewrite href into javascript:).
_SVG_ELEMENTS = frozenset(
    {
        "svg", "g", "defs", "symbol", "use", "title", "desc", "metadata", "style",
        "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
        "text", "tspan", "textPath",
        "linearGradient", "radialGradient", "stop", "pattern",
        "clipPath", "mask", "marker",
        "filter", "feBlend", "feColorMatrix", "feComponentTransfer", "feComposite",
        "feFlood", "feGaussianBlur", "feMerge", "feMergeNode", "feMorphology",
        "feOffset", "feFuncR", "feFuncG", "feFuncB", "feFuncA",
        "feDropShadow",
    }
)  # fmt: skip
# Any url() that isn't a fragment reference to something in the same file.
_EXTERNAL_URL = re.compile(r"url\s*\(\s*+['\"]?+\s*+(?!#)", re.IGNORECASE)
_PROCESSING_INSTRUCTION = re.compile(r"<\?(?!xml\s)", re.IGNORECASE)
_CSS_DENY = ("@import", "javascript:", "expression(", "\\")


@deconstructible
class SVGValidator:
    """
    Accepts only plain vector SVG. Rejects rather than sanitizes, anything
    that could run script or load something from elsewhere is an error.
    """

    def __init__(self, max_size: int = 200 * 1024):
        self.max_size = max_size

    def __call__(self, file):
        from lxml import etree

        if file.size > self.max_size:
            raise ValidationError(
                _("File too large. Max size: %s") % _fmt_bytes(self.max_size)
            )
        file.seek(0)
        data = file.read()
        file.seek(0)
        # UTF-8 only, so the DOCTYPE check can't be dodged with another encoding.
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValidationError(_("SVG must be UTF-8 encoded."))
        lowered = text.lower()
        if "<!doctype" in lowered or "<!entity" in lowered:
            raise ValidationError(_("SVG must not contain a DOCTYPE or entities."))
        # Only the XML declaration. Others, i.e. xml-stylesheet, may sit outside root.
        if _PROCESSING_INSTRUCTION.search(text):
            raise ValidationError(_("SVG must not contain processing instructions."))
        parser = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
            huge_tree=False,
        )
        try:
            root = etree.fromstring(data, parser)
        except etree.XMLSyntaxError:
            raise ValidationError(_("Not a valid SVG file."))
        if root.tag != f"{{{_SVG_NS}}}svg":
            raise ValidationError(_("Not a valid SVG file."))
        for el in root.iter():
            if isinstance(el, etree._Comment):
                continue
            if not isinstance(el.tag, str):
                raise ValidationError(_("Not a valid SVG file."))
            self._check_element(el)

    def _check_element(self, el):
        from lxml import etree

        qname = etree.QName(el)
        if qname.namespace == _SVG_NS:
            if qname.localname not in _SVG_ELEMENTS:
                raise ValidationError(
                    _("SVG element not allowed: %s") % qname.localname
                )
            if qname.localname == "style":
                self._check_css(el.text or "")
        elif qname.namespace not in _SVG_EDITOR_NAMESPACES:
            raise ValidationError(_("SVG element not allowed: %s") % qname.localname)
        for name, value in el.attrib.items():
            attr = etree.QName(name)
            if attr.namespace not in (None, _XLINK_NS, _XML_NS) and (
                attr.namespace not in _SVG_EDITOR_NAMESPACES
            ):
                raise ValidationError(_("SVG attribute not allowed: %s") % name)
            local = attr.localname.lower()
            if local.startswith("on"):
                raise ValidationError(_("SVG attribute not allowed: %s") % local)
            if local == "href" and not value.strip().startswith("#"):
                raise ValidationError(_("SVG may only link within the file."))
            self._check_css(value)

    @staticmethod
    def _check_css(value: str):
        lowered = value.lower()
        if _EXTERNAL_URL.search(value) or any(x in lowered for x in _CSS_DENY):
            raise ValidationError(_("SVG must not reference external resources."))


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


class DuplicateItemsError(ValueError):
    """Raised when a sequence that must hold unique items does not.

    Replaces pydantic v1's ``conlist(..., unique_items=True)``, which was
    removed outright in v2.
    """


def ensure_unique(value):
    """Reject sequences containing duplicates, passing anything else through.

    Unlike ``conlist(unique_items=True)`` this runs *after* field coercion, so
    items that are only distinct before coercion -- e.g. under
    ``constr(to_lower=True, strip_whitespace=True)`` -- are correctly seen as
    duplicates. That was a documented misbehaviour of the pydantic v1 form.

    Items need not be hashable; ``repr`` is used as the identity key, which is
    deterministic for the scalars, lists and models this is applied to.

    >>> ensure_unique([1, 2, 3])
    [1, 2, 3]
    >>> ensure_unique(["a", "a"])
    Traceback (most recent call last):
    ...
    DuplicateItemsError: Items must be unique
    >>> ensure_unique([["a"], ["a"]])
    Traceback (most recent call last):
    ...
    DuplicateItemsError: Items must be unique

    Non-sequences are returned untouched:

    >>> ensure_unique(None) is None
    True
    """
    if not isinstance(value, (list, tuple)):
        return value
    seen: set[str] = set()
    for item in value:
        key = repr(item)
        if key in seen:
            raise DuplicateItemsError("Items must be unique")
        seen.add(key)
    return value
