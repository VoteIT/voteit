from voteit import organisation
from voteit.core.testing import load_doctests


def load_tests(loader, tests, pattern):
    load_doctests(tests, organisation)
    return tests
