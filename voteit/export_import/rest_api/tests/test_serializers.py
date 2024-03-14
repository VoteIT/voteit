import os

from django.test import TestCase

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(_TESTS_DIR, "fixtures")


class ImportSerializerTests(TestCase):

    @property
    def _cut(self):
        from voteit.export_import.rest_api.serializers import FileSerializer

        return FileSerializer

    # def test_empty_file(self):
    #     with open(os.path.join(FIXTURES, "empty.txt"), "r") as f:
    #         serializer = self._cut(data={"file": f.read()})
    #         breakpoint()
