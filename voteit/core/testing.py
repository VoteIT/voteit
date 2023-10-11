""" Testing helpers"""
from __future__ import annotations
import doctest
from contextlib import contextmanager
from pkgutil import walk_packages
from time import perf_counter

from django.contrib.auth import get_user_model
from django.db.transaction import get_connection

user_tag = """
<span class="mention" data-index="0" data-denotation-char="@" data-id="{user_pk}" data-value="{name}">
<span contenteditable="false"><span class="ql-mention-denotation-char">@</span>{name}</span></span>
"""


def mk_usertag(value, name="Jane Doe", any=False) -> str:
    User = get_user_model()
    if isinstance(value, User):
        return user_tag.format(user_pk=value.pk, name=name)
    try:
        value = int(value)
    except ValueError:
        pass
    if isinstance(value, int):
        return user_tag.format(user_pk=value, name=name)
    if any:
        return user_tag.format(user_pk=value, name=name)
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


class FakeCommit:
    """
    A very destructive context manager that will wreak havoc if you use it outside of unittests!
    So don't!

    So why does it exist?
    Most unittests start with mock data that's part of the tests own transaction.
    So if we want to test on_commit hooks, it becomes very problematic since that initial test data may
    have caused commit hooks - and theres no way we can start a new atomic transaction
    within a regular unittest. (It does work with TransactionTestCase but that's painfully slow)
    """

    def __enter__(self):
        """
        Remove staged all on_commit methods on enter - yes this will destroy them for the
        atomic block that's active!
        """
        self.connection = get_connection()
        self.connection.run_on_commit = []

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Execute all on_commit hooks and cleanup.
        """
        current_run_on_commit = self.connection.run_on_commit
        self.connection.run_on_commit = []
        while current_run_on_commit:
            items = current_run_on_commit.pop(0)
            # Django 4.2 has 3 args, <4.2 only 2
            items[1]()


@contextmanager
def exectime() -> float:
    start = perf_counter()
    yield lambda: perf_counter() - start
