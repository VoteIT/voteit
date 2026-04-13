"""Testing helpers"""

from __future__ import annotations
import doctest
import random
from pkgutil import walk_packages
from typing import Generator
from typing import TYPE_CHECKING

from django.db import transaction
from envelope.testing import testing_channel_layers_setting  # noqa
from django.contrib.auth import get_user_model
from django.db.transaction import get_connection

from voteit.core.utils import exectime  # noqa

if TYPE_CHECKING:
    from rest_framework.test import APITestCase


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


class SetSeed:
    """
    Simply set a specific seed then go back to sys default
    """

    def __enter__(self, seed=1337):
        random.seed(seed)

    def __exit__(self, exc_type, exc_value, traceback):
        random.seed()


def run_permission_tests(
    tester: APITestCase,
    *,
    url: str,
    data: dict = None,
    method: str = "get",
    expected: list | tuple,
) -> Generator[tuple, None, None]:
    """

    Returns a generator with test function and args.
    Run test like:

        for func, args in run_permission_tests(
            self,
            url=http://someurl,
            data={'whatever': 1},
            method="POST",
            expected=[
                [None, 401],
                [self.participant, 403],
                [self.outsider, 403],
                [self.moderator, 201, {'partial': 'Hello'],
            ],
        ):
            func(*args)

    """
    if data is None:
        data = {}
    for row in expected:
        if len(row) not in (2, 3):
            yield tester.fail, [f"expected must have 2 or 3 items per row. Got: {row}"]
        user = row[0]
        if user:
            tester.client.force_login(user)
        else:
            tester.client.logout()
        expected_status = row[1]
        if not isinstance(expected_status, int):
            yield (
                tester.fail,
                [f"item 2 of each row must be in int, got {expected_status}"],
            )
        try:
            partial_response = row[2]
            if not isinstance(partial_response, (dict, list)):
                yield (
                    tester.fail,
                    [
                        f"item 3 of each row must be dict, list or not exist, got {partial_response}"
                    ],
                )
        except IndexError:
            partial_response = None
        sid = transaction.savepoint()
        with tester.subTest(
            user=user,
            expected_status=expected_status,
            url=url,
            data=data,
            partial_response=partial_response,
        ):
            response = getattr(tester.client, method.lower())(url, data, format="json")
            try:
                json_response = response.json()
            except TypeError:
                json_response = None
            yield (
                tester.assertEqual,
                [
                    response.status_code,
                    expected_status,
                    f"{url}: {user} got {response.status_code} instead of {expected_status}.\n{json_response}",
                ],
            )
            if partial_response is not None:
                if json_response is None:
                    yield tester.assertEqual, [json_response, None]  # To produce error
                elif isinstance(json_response, list):  # Maybe fix mapping later on
                    yield (
                        tester.assertEqual,
                        [partial_response, json_response],
                    )
                else:
                    yield (
                        tester.assertDictEqual,
                        [
                            partial_response,
                            {
                                k: v
                                for k, v in json_response.items()
                                if k in partial_response
                            },
                        ],
                    )
        transaction.savepoint_rollback(sid)
