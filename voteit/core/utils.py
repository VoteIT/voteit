from __future__ import annotations

import re
from inspect import isclass
from typing import Optional
from typing import Set
from typing import Type
from typing import Union

from bleach import ALLOWED_ATTRIBUTES
from bleach import ALLOWED_TAGS
from bleach import Cleaner
from bs4 import BeautifulSoup
from django.db.models import Model


_tag_pattern = re.compile(r"#([\w\-]+)")
# FIXME: Do a proper regex. I'm crappy with this /rho
_userid_pattern = re.compile(r"@([\w\d]+)")


def get_tags(text: str, lower=True) -> Set[str]:
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
        return set([x.lower() for x in _tag_pattern.findall(text)])
    return set(_tag_pattern.findall(text))


def get_mentions(text: str) -> Set[int]:
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


def get_tagged_userids(text: str) -> Set:
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

    >>> sorted(get_tagged_userids(mk_usertag("abc")))
    []

    >>> sorted(get_tagged_userids(mk_usertag("abc123")))
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


def get_tagged_hashtags(text: str, lower=True) -> Set:
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


_allowed_attributes = ALLOWED_ATTRIBUTES.copy()
_allowed_attributes["a"].extend(["data-userid", "data-tag"])
_allowed_attributes.setdefault("span", [])
_allowed_attributes["span"].extend(
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
_allowed_tags = ALLOWED_TAGS + ["p", "span", "br"]


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
    cleaner = Cleaner(strip=False, tags=_allowed_tags, attributes=_allowed_attributes)
    # FIXME: The cleaned version of this moves exclamation mark inside the tag? '<a data-userid="1"/>!'
    return cleaner.clean(text)


def relaxed_clean_html(text: str):
    """ Clean HTML for moderators and trusted users. Note that trusted users may have viruses too..."""
    # FIXME: Implement
    raise NotImplementedError()


def get_content_registry():
    from .registries import content_types

    return content_types


def get_permission_registry():
    from .registries import permissions

    return permissions


def get_model_by_shortname(name, default=None) -> Optional[Type[Model]]:
    name = name.lower()
    reg = get_content_registry()
    return reg.get(name, default)


def get_model_shortname(model: Union[Type[Model], Model]) -> str:
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
