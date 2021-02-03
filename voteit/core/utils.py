import re
from typing import Set

from bleach import Cleaner, ALLOWED_TAGS, ALLOWED_ATTRIBUTES
from bs4 import BeautifulSoup

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
    Userid tags look like: <a href data-userid="123"/> or
    <a href data-userid="123">This part is ignored</a>

    >>> sorted(get_tagged_userids('<a href data-userid="123"/>'))
    [123]

    >>> sorted(get_tagged_userids('<a href data-userid="abc"/>'))
    []

    >>> sorted(get_tagged_userids('<a href data-userid="abc123"/>'))
    []

    >>> sorted(get_tagged_userids('<a href data-userid="1">Just ignore me</a> and <span><a data-userid="2"></a></span>'))
    [1, 2]

    >>> sorted(get_tagged_userids('<span data-userid="1">Just ignore me and my tag</span>'))
    []
    """
    soup = BeautifulSoup(text, features="lxml")
    found = set()
    for item in soup.find_all(name="a", attrs={"data-userid": _userid_num_match}):
        found.add(int(item["data-userid"]))
    return found


_single_tag_pattern = re.compile(r"^[#]?([\w\-]+)")


def get_tagged_hashtags(text: str, lower=True) -> Set:
    """
    Tags come in a-blocks with data-tag attribute. The contents is the tag.
    <a data-tag>#Hej</a>

    >>> sorted(get_tagged_hashtags('<a data-tag>#tag</a>'))
    ['tag']

    Hence without content the tags will be ignored
    >>> get_tagged_hashtags('<a data-tag></a> or <a data-tag />')
    set()

    Tags can be with or without hashtag
    >>> sorted(get_tagged_hashtags('<a data-tag>#meenie</a> or <a data-tag>moo</a>'))
    ['meenie', 'moo']

    Tags are lowercased by default, ie removing any duplicates regardless of format
    >>> sorted(get_tagged_hashtags('<a data-tag>#aaa</a> <a data-tag>AAA</a>'))
    ['aaa']

    Pass lower=False to override
    >>> sorted(get_tagged_hashtags('<a data-tag>#Same</a> <a data-tag>same</a>', lower=False))
    ['Same', 'same']
    """
    soup = BeautifulSoup(text, features="lxml")
    found = set()
    for item in soup.select("a[data-tag]"):
        if _single_tag_pattern.match(item.text):
            v = item.text.replace("#", "")
            if lower:
                found.add(v.lower())
            else:
                found.add(v)
    return found


_allowed_attributes = ALLOWED_ATTRIBUTES.copy()
_allowed_attributes["a"].extend(["data-userid", "data-tag"])


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
    cleaner = Cleaner(strip=False, attributes=_allowed_attributes)
    # FIXME: The cleaned version of this moves exclamation mark inside the tag? '<a data-userid="1"/>!'
    return cleaner.clean(text)


def relaxed_clean_html(text: str):
    """ Clean HTML for moderators and trusted users. Note that trusted users may have viruses too..."""
    # FIXME: Implement
    raise NotImplementedError()
