from django.test import SimpleTestCase

from pydantic import ValidationError

from voteit.invites.schemas import RowColInvitesBaseSchema


class CheckImportantDataOutsideReadColumnsTests(SimpleTestCase):
    """
    The error message is built from row indices and raw cells, neither of which
    is guaranteed to be a string -- and both callers of this schema wrap it in
    a bare ``except Exception`` that shows ``str(exc)`` to the operator, so a
    TypeError here surfaces as the entire error report.
    """

    def _message(self, columns, rows) -> str:
        with self.assertRaises(ValidationError) as cm:
            RowColInvitesBaseSchema(columns=columns, rows=rows)
        return str(cm.exception)

    def test_single_offending_row_names_its_line(self):
        msg = self._message(["email"], [["a@x.com", "extra"]])
        self.assertIn("a@x.com', 'extra", msg)

    def test_a_few_offending_rows_list_the_remaining_line_numbers(self):
        msg = self._message(
            ["email"],
            [["a@x.com", "x"], ["b@x.com", "y"], ["c@x.com", "z"]],
        )
        self.assertIn("1, 2 are also too long", msg)

    def test_many_offending_rows_report_a_count(self):
        rows = [[f"{i}@x.com", "x"] for i in range(7)]
        msg = self._message(["email"], rows)
        self.assertIn("6 other lines", msg)

    def test_non_string_cells_are_rendered_not_raised_on(self):
        msg = self._message(["email"], [["a@x.com", None, 1]])
        self.assertIn("a@x.com", msg)
