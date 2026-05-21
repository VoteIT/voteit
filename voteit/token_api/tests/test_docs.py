import doctest
import os

from django.test import TestCase


class TokenAPIDocTests(TestCase):
    FLAGS = (
        doctest.NORMALIZE_WHITESPACE
        | doctest.ELLIPSIS
        | doctest.FAIL_FAST
        | doctest.IGNORE_EXCEPTION_DETAIL
    )

    def test_readme(self):
        result = doctest.testfile(
            os.path.join("..", "README.md"),
            optionflags=self.FLAGS,
            extraglobs={"test": self},
        )
        if result.failed:
            self.fail(f"README.md doctest has {result.failed} failures")
