from voteit import participant_number
from voteit.core.testing import load_doctests


def load_tests(loader, tests, pattern):
    load_doctests(tests, participant_number)
    return tests
