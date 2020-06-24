import doctest
import os

from django.test import TestCase


class CoreDocTests(TestCase):

    DOCS_RELATIVE = os.path.join("..", "..", "..", "docs")

    def _docfile(self, fn):
        return os.path.join(self.DOCS_RELATIVE, fn)

    def _doctest_file(self, fn):
        doctest.testfile(os.path.join(self.DOCS_RELATIVE, fn))

    def test_narrative_readme(self):
        self._doctest_file("narrative.md")


# def load_tests(loader, tests, ignore):
#     from voteit.core import role
#     opts = doctest.NORMALIZE_WHITESPACE | doctest.ELLIPSIS | doctest.FAIL_FAST
#     tests.addTests(doctest.DocTestSuite(role, optionflags=opts))
#     return tests
