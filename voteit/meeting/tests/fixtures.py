import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
DIALECT_FIXTURES = os.path.join(TESTS_DIR, "dialect_fixtures")
BAD_DIALECT_FIXTURES = os.path.join(TESTS_DIR, "bad_dialect_fixtures")
CYCLIC_DIALECT_FIXTURES = os.path.join(TESTS_DIR, "cyclic_dialect_fixtures")
