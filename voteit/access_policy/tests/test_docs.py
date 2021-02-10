from voteit import access_policy
from voteit.core.testing import load_doctests


def load_tests(loader, tests, pattern):
    load_doctests(tests, access_policy)
    return tests
