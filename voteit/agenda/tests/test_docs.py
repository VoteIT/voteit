from voteit import agenda
from voteit.core.testing import load_doctests


def load_tests(loader, tests, pattern):
    load_doctests(tests, agenda)
    return tests
