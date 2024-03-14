from voteit.core.testing import load_doctests

from voteit import export_import


def load_tests(loader, tests, pattern):
    load_doctests(tests, export_import)
    return tests
