import os

import voteit.invites.tests


FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(voteit.invites.tests.__file__)), "fixtures"
)


def fixture_file(filename) -> str:
    return os.path.join(FIXTURES_DIR, filename)


def get_unvalidated_fixture_content(filename) -> tuple[list[str], list[list[str]]]:
    with open(fixture_file(filename)) as f:
        data = f.read()
    rows = [x.split("\t") for x in data.splitlines()]
    # Pop header
    return rows.pop(0), rows
