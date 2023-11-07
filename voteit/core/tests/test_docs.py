import doctest
import os

from django.test import TestCase

from voteit import core
from voteit.core.testing import load_doctests


class CoreDocTests(TestCase):
    DOCS_RELATIVE = os.path.join("..", "..", "..", "docs")
    FLAGS = (
        doctest.NORMALIZE_WHITESPACE
        | doctest.ELLIPSIS
        | doctest.FAIL_FAST
        | doctest.IGNORE_EXCEPTION_DETAIL
    )

    def _docfile(self, fn):
        return os.path.join(self.DOCS_RELATIVE, fn)

    def _doctest_file(self, fn):
        result = doctest.testfile(
            os.path.join(self.DOCS_RELATIVE, fn),
            optionflags=self.FLAGS,
            extraglobs={"test": self},
        )
        if result.failed:
            self.fail(f"DocTest {fn} has {result.failed} fails")

    def test_narrative_readme(self):
        self._doctest_file("narrative.md")


def load_tests(loader, tests, pattern):
    load_doctests(tests, core)
    return tests
