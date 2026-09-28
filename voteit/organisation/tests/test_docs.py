import doctest
import os

from django.test import TestCase

from voteit import organisation
from voteit.core.testing import load_doctests

FLAGS = (
    doctest.NORMALIZE_WHITESPACE
    | doctest.ELLIPSIS
    | doctest.FAIL_FAST
    | doctest.IGNORE_EXCEPTION_DETAIL
)


class OrganisationDocTests(TestCase):
    def _doctest_file(self, fn):
        result = doctest.testfile(
            os.path.join("..", fn), optionflags=FLAGS, extraglobs={"test": self}
        )
        if result.failed:
            self.fail(f"DocTest {fn} has {result.failed} fails")

    def test_readme(self):
        self._doctest_file("README.md")


def load_tests(loader, tests, pattern):
    load_doctests(tests, organisation)
    return tests
