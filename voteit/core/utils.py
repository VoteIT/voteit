import re
from typing import Set

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


def html_should_be_escaped(text: str) -> bool:
    """Simple match for dangerous things.
    >>> html_should_be_escaped("Hello<script>")
    True
    """
    # FIXME: Match any other chars? Like & but not &amp;
    return "<" in text or ">" in text
