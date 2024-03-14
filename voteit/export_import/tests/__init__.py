import os

import yaml

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def read_fixture(fn: str) -> dict:
    with open(os.path.join(FIXTURES_DIR, fn)) as f:
        return yaml.full_load(f)
