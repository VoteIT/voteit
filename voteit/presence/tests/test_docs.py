from voteit import presence
from voteit.core.testing import load_doctests


def load_tests(loader, tests, pattern):
    load_doctests(tests, presence)
    return tests
