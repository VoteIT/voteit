from voteit import invites
from voteit.core.testing import load_doctests


def load_tests(loader, tests, pattern):
    load_doctests(tests, invites)
    return tests
