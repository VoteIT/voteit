import doctest
import os

from django.test import TestCase


class CoreDocTests(TestCase):

    DOCS_RELATIVE = os.path.join("..", "..", "..", "docs")

    def _docfile(self, fn):
        return os.path.join(self.DOCS_RELATIVE, fn)

    def _doctext_file(self, fn):
        doctest.testfile(os.path.join(self.DOCS_RELATIVE, fn))

    def test_narrative_readme(self):
        self._doctext_file("narrative.md")
