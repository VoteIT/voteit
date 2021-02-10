from voteit import reactions
from voteit.core.testing import load_doctests


def load_tests(loader, tests, pattern):
    load_doctests(tests, reactions)
    return tests
