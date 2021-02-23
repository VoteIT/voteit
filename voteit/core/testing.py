""" Testing helpers"""
from __future__ import annotations
import doctest
from pkgutil import walk_packages
from typing import TYPE_CHECKING, Set, Optional, Dict

if TYPE_CHECKING:
    from django.db.models import Model

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


_PERMS_TO_TEST = ("ADD", "CHANGE", "DELETE", "VIEW")


def find_bad_permission_names(permissions, model: Model) -> Optional[Dict]:
    """Returns non-django-compliant names from a permission object
    May return a dict with failing permissions where the key is the correct one

    add: user.has_perm("foo.add_bar")
    change: user.has_perm("foo.change_bar")
    delete: user.has_perm("foo.delete_bar")
    view: user.has_perm("foo.view_bar")
    """
    from django.contrib.contenttypes.models import ContentType

    ct: ContentType = ContentType.objects.get_for_model(model)
    app_name, model_name = ct.natural_key()
    results = {}
    for perm_name in _PERMS_TO_TEST:
        perm = getattr(permissions, perm_name, None)
        if perm is not None:
            dj_perm = f"{app_name}.{perm_name.lower()}_{model_name}"
            if dj_perm != perm:
                results[dj_perm] = perm
    if results:
        return results
