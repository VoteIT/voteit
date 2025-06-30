from voteit import participant_tags
from voteit.core.testing import load_doctests


def load_tests(loader, tests, pattern):
    load_doctests(tests, participant_tags)
    return tests
