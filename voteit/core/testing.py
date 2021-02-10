""" Testing helpers"""
import doctest
from pkgutil import walk_packages

user_tag = """
<span class="mention" data-index="0" data-denotation-char="@" data-id="{userid}" data-value="{name}">
<span contenteditable="false"><span class="ql-mention-denotation-char">@</span>{name}</span></span>
"""


def mk_usertag(userid, name="Jane Doe") -> str:
    return user_tag.format(userid=userid, name=name)


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
    opts = doctest.NORMALIZE_WHITESPACE | doctest.ELLIPSIS | doctest.FAIL_FAST
    for importer, name, ispkg in walk_packages(
        package.__path__, package.__name__ + "."
    ):
        tests.addTests(doctest.DocTestSuite(name, optionflags=opts))
