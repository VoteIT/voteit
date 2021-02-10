from voteit import discussion
from voteit.core.testing import load_doctests


def load_tests(loader, tests, pattern):
    load_doctests(tests, discussion)
    return tests
