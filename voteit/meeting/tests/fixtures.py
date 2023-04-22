import os

from voteit.meeting.dialects import DialectScript

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
DIALECT_FIXTURES = os.path.join(TESTS_DIR, "dialect_fixtures")
BAD_DIALECT_FIXTURES = os.path.join(TESTS_DIR, "bad_dialect_fixtures")
CYCLIC_DIALECT_FIXTURES = os.path.join(TESTS_DIR, "cyclic_dialect_fixtures")


class DialectScriptTitleChanger(DialectScript):
    def install(self, meeting):
        meeting.title = "I did stuff"
        meeting.save()

    def remove(self, meeting):
        meeting.title = "Gone again"
        meeting.save()
