from __future__ import annotations

import re
from copy import deepcopy
from inspect import isclass
from random import randint
from typing import TYPE_CHECKING

from bleach import ALLOWED_ATTRIBUTES
from bleach import ALLOWED_TAGS
from bleach import Cleaner
from bs4 import BeautifulSoup
from django.db.models import Model
from django.utils.text import slugify

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.core.permissions import PermissionRegistry
    from voteit.core.registries import ContentRegistry


_tag_pattern = re.compile(r"#([\w\-]+)")
# FIXME: Do a proper regex. I'm crappy with this /rho
_userid_pattern = re.compile(r"@([\w\d]+)")


def get_tags(text: str, lower=True) -> set[str]:
    """
    Return a set of matched tags
    >>> sorted(get_tags("#hello #world #hello"))
    ['hello', 'world']

    Tags can be any case, but will be lowercased if needed
    >>> sorted(get_tags("#Hello #world #hello"))
    ['hello', 'world']
    >>> sorted(get_tags("#Hello #world #hello", lower=False))
    ['Hello', 'hello', 'world']

    Hyphens and underscores are included
    >>> sorted(get_tags("#He-llo #_world_ #hello"))
    ['_world_', 'he-llo', 'hello']

    ...but dots or other separators end the tag.
    >>> sorted(get_tags("#Hello!World #world."))
    ['hello', 'world']

    International chars should work too
    >>> sorted(get_tags("#Räck mig din hand #kära du!"))
    ['kära', 'räck']
    """
    if lower:
        return {x.lower() for x in _tag_pattern.findall(text)}
    return set(_tag_pattern.findall(text))


def get_mentions(text: str) -> set[int]:
    """
    Return a set of matched integers that (probably) corresponds to users
    >>> sorted(get_mentions("What's up @1"))
    [1]

    Mixin it with other chars don't match it though
    >>> sorted(get_mentions("@123jeff is not a username"))
    []

    Separators do end the match
    >>> sorted(get_mentions("@1, @2,@3 and @4! but not @-5"))
    [1, 2, 3, 4]
    """
    res = set()
    for x in _userid_pattern.findall(text):
        try:  # Better regex instead :)
            res.add(int(x))
        except ValueError:
            pass
    return res


_userid_num_match = re.compile(r"^[\d]+$")


def get_tagged_userids(text: str) -> set:
    """
    Userid tags look like:
    <span class="mention" data-index="0" data-denotation-char="@" data-id="${userid}" data-value="${name}">
        <span contenteditable="false">
            <span class="ql-mention-denotation-char">@</span>
            ${name}
        </span>
    </span>

    Since they're kind of long we'll use a helper for this test

    >>> from voteit.core.testing import mk_usertag
    >>> sorted(get_tagged_userids(mk_usertag(123)))
    [123]

    >>> sorted(get_tagged_userids(mk_usertag("abc", any=True)))
    []

    >>> sorted(get_tagged_userids(mk_usertag("abc123", any=True)))
    []

    >>> sorted(get_tagged_userids(mk_usertag("1") + " and " + mk_usertag("2")))
    [1, 2]
    """
    soup = BeautifulSoup(text, features="lxml")
    found = set()
    # data-denotation-char="@"
    for item in soup.find_all(
        name="span", attrs={"data-denotation-char": "@", "data-id": _userid_num_match}
    ):
        found.add(int(item["data-id"]))
    return found


_single_tag_pattern = re.compile(r"^[#]?([\w\-]+)")


def get_tagged_hashtags(text: str, lower=True) -> set:
    """
    Tags from Quills look like this:
    <span class="mention" data-index="0" data-denotation-char="#" data-id="{tag}" data-value="{tag}">
        <span contenteditable="false">
            <span class="ql-mention-denotation-char">#</span>
            {tag}
        </span>
    </span>

    So we have a helper function to create them
    >>> from voteit.core.testing import mk_hashtag

    >>> sorted(get_tagged_hashtags(mk_hashtag('tag')))
    ['tag']

    Tags are lowercased by default, ie removing any duplicates regardless of format
    >>> sorted(get_tagged_hashtags(mk_hashtag('aaa') + " and " + mk_hashtag('AAA')))
    ['aaa']

    Pass lower=False to override
    >>> sorted(get_tagged_hashtags(mk_hashtag('same') + mk_hashtag('Same'), lower=False))
    ['Same', 'same']
    """
    soup = BeautifulSoup(text, features="lxml")
    found = set()
    for item in soup.find_all(
        name="span", attrs={"data-denotation-char": "#", "data-id": _single_tag_pattern}
    ):
        if lower:
            found.add(item["data-id"].lower())
        else:
            found.add(item["data-id"])
    return found


_STRICT = {
    "attributes": deepcopy(ALLOWED_ATTRIBUTES),
    "tags": set(ALLOWED_TAGS) | {"p", "span", "br"},
}
_STRICT["attributes"]["a"].extend(["data-userid", "data-tag"])
_STRICT["attributes"].setdefault("span", []).extend(
    [
        "class",
        "contenteditable",
        "data-denotation-char",
        "data-id",
        "data-index",
        "data-value",
        "ql-mention-denotation-char",
    ]
)


def strict_clean_html(text: str):
    """
    Clean HTML for non-trusted users, for instance anonymous.

    >>> strict_clean_html('<a href="javascript:1+1">Hi</a>')
    '<a>Hi</a>'

    Our special tags should be kept
    >>> strict_clean_html('Hello <a data-userid="1">!</a>')
    'Hello <a data-userid="1">!</a>'

    """
    # The cleaner instance isn't thread-safe
    # https://bleach.readthedocs.io/en/latest/clean.html
    cleaner = Cleaner(strip=False, **_STRICT)
    # FIXME: The cleaned version of this moves exclamation mark inside the tag? '<a data-userid="1"/>!'
    return cleaner.clean(text)


_relaxed = deepcopy(_STRICT)
_relaxed["tags"].update(["h2", "h3", "h4", "sup", "sub", "img", "iframe"])
for tag in "h2", "h3", "h4", "p", "blockquote":
    _relaxed["attributes"].setdefault(tag, []).append("class")
_relaxed["attributes"].setdefault("img", []).append("src")
_relaxed["attributes"].setdefault("iframe", []).extend(
    ["class", "frameborder", "allowfullscreen", "src"]
)


def relaxed_clean_html(text: str):
    """Clean HTML for moderators and trusted users. Note that trusted users may have viruses too..."""
    cleaner = Cleaner(strip=False, **_relaxed)
    # FIXME: The cleaned version of this moves exclamation mark inside the tag? '<a data-userid="1"/>!'
    return cleaner.clean(text)


def get_content_registry() -> ContentRegistry:
    from .registries import content_types

    return content_types


def get_permission_registry() -> PermissionRegistry:
    from .registries import permissions

    return permissions


def get_model_by_shortname(name, default=None) -> type[Model] | None:
    name = name.lower()
    reg = get_content_registry()
    return reg.get(name, default)


def get_model_shortname(model: type[Model] | Model) -> str:
    """
    Fetch model shortname from class or instance
    >>> from voteit.meeting.models import Meeting
    >>> get_model_shortname(Meeting)
    'meeting'
    >>> get_model_shortname(Meeting())
    'meeting'

    Should also work with types that lack name attr or has it set to something else
    >>> from django.contrib.auth.models import Permission
    >>> get_model_shortname(Permission)
    'permission'
    """
    if isinstance(model, Model):
        model = model.__class__
    elif isclass(model) and issubclass(model, Model):
        pass
    else:
        raise ValueError(f"{model} is not an instance or classed based on Django Model")
    name = getattr(model, "name", None)
    if isinstance(name, str):
        return name
    return model.__name__.lower()


def get_model_by_type(value: type[Model] | Model | str) -> set[type[Model]]:
    """
    Fetch all models that inherits from that class
    >>> from voteit.meeting.models import Meeting
    >>> res1 = get_model_by_type("meeting")
    >>> res2 = get_model_by_type(Meeting)
    >>> res3 = get_model_by_type(Meeting())
    >>> res1 == res2 == res3
    True
    >>> Meeting in res1
    True
    >>> from voteit.core.models import BaseContent
    >>> res = get_model_by_type(BaseContent)
    >>> Meeting in res
    True

    """
    if isinstance(value, str):
        model = get_model_by_shortname(value)
        if model is None:
            raise KeyError(f"No model named {value}")
    elif isinstance(value, Model):
        model = value.__class__
    else:
        model = value
    assert isclass(model)
    found = set()
    for klass in get_content_registry().values():
        if issubclass(klass, model):
            found.add(klass)
    return found


_cached_available_transitions = {}


def prepare_available_transitions():
    from voteit.core.rest_api.serializers import BaseFSMTransitonSerializer

    content_reg = get_content_registry()
    for (name, content) in content_reg.items():
        # FIXME: This may change, but currently all models use "state" as attr.
        if hasattr(content, "state"):
            serializer = BaseFSMTransitonSerializer(
                list(content.state.field.get_all_transitions(content)), many=True
            )
            _cached_available_transitions[name] = serializer.data


def get_available_transitions() -> dict:
    return _cached_available_transitions


def generate_valid_userid(user: AbstractUser) -> str | None:
    """
    Try to generate a valid userid for a specific user. In case one can't be found safely, simply return None
    """
    # Avoid circular
    from voteit.core.validators import valid_userid
    from voteit.meeting.models import MeetingGroup

    try:
        slugified_name = suggestion = valid_userid(slugify(user.get_full_name()))
    except ValueError:
        # Log bad names?
        return None
    # Create base querysets
    if user.organisation is None:  # For testing
        user_qs = user.__class__.objects.exclude(pk=user.pk)  # Omit current user
        group_qs = MeetingGroup.objects.all()
    else:
        user_qs = user.organisation.users.exclude(pk=user.pk)  # Omit current user
        group_qs = MeetingGroup.objects.filter(meeting__organisation=user.organisation)
    for i in range(10):
        if not (
            user_qs.filter(userid=suggestion).exists()
            or group_qs.filter(groupid=suggestion).exists()
        ):
            return suggestion
        suggestion = f"{slugified_name}-{randint(1, 9999)}"
