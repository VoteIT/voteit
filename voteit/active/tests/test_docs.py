from voteit import active
from voteit.core.testing import load_doctests


def load_tests(loader, tests, pattern):
    load_doctests(tests, active)
    return tests
