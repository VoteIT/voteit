from voteit import stats
from voteit.core.testing import load_doctests


def load_tests(loader, tests, pattern):
    load_doctests(tests, stats)
    return tests
