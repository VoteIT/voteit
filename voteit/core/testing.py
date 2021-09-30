""" Testing helpers"""
from __future__ import annotations
import doctest
from pkgutil import walk_packages

from django.contrib.auth import get_user_model

user_tag = """
<span class="mention" data-index="0" data-denotation-char="@" data-id="{userid}" data-value="{name}">
<span contenteditable="false"><span class="ql-mention-denotation-char">@</span>{name}</span></span>
"""


def mk_usertag(value, name="Jane Doe", any=False) -> str:
    User = get_user_model()
    if isinstance(value, User):
        return user_tag.format(userid=value.pk, name=name)
    try:
        value = int(value)
    except ValueError:
        pass
    if isinstance(value, int):
        return user_tag.format(userid=value, name=name)
    if any:
        return user_tag.format(userid=value, name=name)
    raise TypeError("Must be a user or an int")


hashtag_tag = """
<span class="mention" data-index="0" data-denotation-char="#" data-id="{tag}" data-value="{tag}">
<span contenteditable="false"><span class="ql-mention-denotation-char">#</span>{tag}</span></span> 
"""


def mk_hashtag(tag) -> str:
    return hashtag_tag.format(tag=tag)


def load_doctests(tests, package) -> None:
    """Load doctests from a specific package/module. Must be called from a test_ file with the following function:

    def load_tests(loader, tests, pattern):
        load_doctests(tests, <module>)
        return tests

    Where module is voteit.core for instance.
    """
    opts = (
        doctest.NORMALIZE_WHITESPACE
        | doctest.ELLIPSIS
        | doctest.FAIL_FAST
        | doctest.IGNORE_EXCEPTION_DETAIL
    )
    for importer, name, ispkg in walk_packages(
        package.__path__, package.__name__ + "."
    ):
        tests.addTests(doctest.DocTestSuite(name, optionflags=opts))
