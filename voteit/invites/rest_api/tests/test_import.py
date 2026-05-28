from __future__ import annotations

import io
import os
from http import HTTPStatus

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from voteit.invites.models import MeetingGroupAnnotation
from voteit.invites.models import MeetingInvite
from voteit.invites.rest_api.import_utils import detect_and_parse_file
from voteit.invites.rest_api.import_utils import extract_roles_per_row
from voteit.invites.rest_api.import_utils import parse_invite_file
from voteit.meeting.models import Meeting
from voteit.meeting.workflows import MeetingWf
from voteit.organisation.models import Organisation

User = get_user_model()

URL = "/api/meeting-invites/import/"

# test_import.py lives at: voteit/invites/rest_api/tests/
# Fixtures live at:        voteit/invites/tests/fixtures/
FIXTURES_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "tests", "fixtures")
)


def fixture_bytes(filename: str) -> bytes:
    with open(os.path.join(FIXTURES_DIR, filename), "rb") as f:
        return f.read()


def fixture_file(filename: str) -> io.BytesIO:
    f = io.BytesIO(fixture_bytes(filename))
    f.name = filename
    return f


# ---------------------------------------------------------------------------
# Unit tests — parse_invite_file
# ---------------------------------------------------------------------------


class ParseInviteFileTests(TestCase):
    def test_tsv_tab_separated(self):
        columns, rows = parse_invite_file("email\tgroup\nalice@x.com\tsw\n")
        self.assertEqual(["email", "group"], columns)
        self.assertEqual([["alice@x.com", "sw"]], rows)

    def test_csv_comma_separated(self):
        columns, rows = parse_invite_file("email,group\nalice@x.com,sw")
        self.assertEqual(["email", "group"], columns)
        self.assertEqual([["alice@x.com", "sw"]], rows)

    def test_crlf_line_endings(self):
        columns, rows = parse_invite_file("email\r\nalice@x.com\r\nbob@x.com\r\n")
        self.assertEqual(["email"], columns)
        self.assertEqual([["alice@x.com"], ["bob@x.com"]], rows)

    def test_empty_lines_ignored(self):
        _, rows = parse_invite_file("email\nalice@x.com\n\n\n")
        self.assertEqual(1, len(rows))

    def test_headers_lowercased_and_stripped(self):
        columns, _ = parse_invite_file("  Email  \t  Group  \nalice@x.com\tsw")
        self.assertEqual(["email", "group"], columns)

    def test_cell_values_stripped(self):
        _, rows = parse_invite_file("email\n  alice@x.com  \n")
        self.assertEqual([["alice@x.com"]], rows)

    def test_empty_file_raises(self):
        with self.assertRaises(ValueError):
            parse_invite_file("")

    def test_whitespace_only_raises(self):
        with self.assertRaises(ValueError):
            parse_invite_file("   \n  \n")

    def test_headerless_email_list_auto_detected(self):
        # No column header — just email addresses
        columns, rows = parse_invite_file("alice@x.com\nbob@x.com\n")
        self.assertEqual(["email"], columns)
        self.assertEqual([["alice@x.com"], ["bob@x.com"]], rows)

    def test_bom_stripped_before_calling_parse(self):
        # Serializer decodes bytes with utf-8-sig; verify that the stripped content parses fine
        raw = "email\nalice@x.com".encode("utf-8-sig")
        decoded = raw.decode("utf-8-sig")
        columns, rows = parse_invite_file(decoded)
        self.assertEqual(["email"], columns)


# ---------------------------------------------------------------------------
# Unit tests — detect_and_parse_file
# ---------------------------------------------------------------------------


class DetectAndParseFileTests(TestCase):
    def test_plain_utf8_text_csv(self):
        raw = b"email,group\nalice@x.com,sw\n"
        columns, rows = detect_and_parse_file(raw)
        self.assertEqual(["email", "group"], columns)

    def test_utf8_bom_csv(self):
        raw = "email,group\nalice@x.com,sw\n".encode("utf-8-sig")
        columns, rows = detect_and_parse_file(raw)
        self.assertEqual(["email", "group"], columns)

    def test_tab_separated(self):
        raw = "email\tgroup\nalice@x.com\tsw\n".encode("utf-8")
        columns, rows = detect_and_parse_file(raw)
        self.assertEqual(["email", "group"], columns)

    def test_non_utf8_binary_raises(self):
        with self.assertRaises(ValueError):
            detect_and_parse_file(b"\xff\xfe\xfd\xfc" + b"\x00" * 100)

    def test_corrupt_zip_raises(self):
        # Starts with ZIP magic but is not a valid ZIP
        with self.assertRaises(ValueError):
            detect_and_parse_file(_ZIP_MAGIC + b"\x00" * 50)

    def test_xlsx_fixture(self):
        raw = fixture_bytes("excel_like.xlsx")
        columns, rows = detect_and_parse_file(raw)
        self.assertEqual(["email", "group", "swedish_ssn"], columns)
        self.assertEqual(5, len(rows))

    def test_ods_fixture(self):
        raw = fixture_bytes("open_document.ods")
        columns, rows = detect_and_parse_file(raw)
        self.assertEqual(["email", "group", "swedish_ssn"], columns)
        self.assertEqual(5, len(rows))

    def test_comma_separated_fixture(self):
        raw = fixture_bytes("comma_separated.csv")
        columns, rows = detect_and_parse_file(raw)
        self.assertEqual(["email", "group", "swedish_ssn"], columns)
        self.assertEqual(5, len(rows))

    def test_tab_separated_fixture(self):
        raw = fixture_bytes("tab_separated.tsv")
        columns, rows = detect_and_parse_file(raw)
        self.assertEqual(["email", "group", "swedish_ssn"], columns)
        self.assertEqual(5, len(rows))

    def test_emails_txt_fixture(self):
        raw = fixture_bytes("emails.txt")
        columns, rows = detect_and_parse_file(raw)
        self.assertEqual(["email"], columns)
        self.assertEqual(3, len(rows))

    def test_file_too_large_raises(self):
        from voteit.invites.rest_api.import_utils import MAX_UPLOAD_BYTES

        raw = b"email\n" + b"a@b.com\n" * (MAX_UPLOAD_BYTES // 8)
        with self.assertRaises(ValueError) as cm:
            detect_and_parse_file(raw)
        self.assertIn("too large", str(cm.exception).lower())

    def test_zip_bomb_xml_entry_raises(self):
        """A ZIP with a single XML entry larger than the per-entry limit must be rejected."""
        from voteit.invites.rest_api.import_utils import _MAX_XML_ENTRY_BYTES
        import zipfile as zf_mod

        buf = io.BytesIO()
        # Write a fake XLSX structure with an oversized sharedStrings entry
        with zf_mod.ZipFile(buf, "w", compression=zf_mod.ZIP_STORED) as zf:
            zf.writestr("[Content_Types].xml", "<Types/>")
            zf.writestr("xl/workbook.xml", "<workbook/>")
            # Write a real entry whose file_size exceeds the limit
            zf.writestr(
                zf_mod.ZipInfo("xl/sharedStrings.xml"),
                b"x" * (_MAX_XML_ENTRY_BYTES + 1),
            )
        with self.assertRaises(ValueError) as cm:
            detect_and_parse_file(buf.getvalue())
        self.assertIn("too large", str(cm.exception).lower())

    def test_fixture_rows_content(self):
        # All spreadsheet fixtures should have identical logical content
        expected_emails = {
            "vader@betahaus.net",
            "luke@betahaus.net",
            "din@betahaus.net",
        }
        for filename in (
            "excel_like.xlsx",
            "open_document.ods",
            "comma_separated.csv",
            "tab_separated.tsv",
        ):
            with self.subTest(filename=filename):
                _, rows = detect_and_parse_file(fixture_bytes(filename))
                emails = {row[0] for row in rows}
                self.assertEqual(
                    expected_emails, emails, f"{filename}: unexpected emails"
                )


# Import this after the function so the test can reference the constant directly
_ZIP_MAGIC = b"PK\x03\x04"


# ---------------------------------------------------------------------------
# Unit tests — extract_roles_per_row
# ---------------------------------------------------------------------------


class ExtractRolesPerRowTests(TestCase):
    def test_no_roles_column_defaults_to_participant(self):
        cols, rows, roles_per_row = extract_roles_per_row(["email"], [["a@x.com"]])
        self.assertEqual(["email"], cols)
        self.assertEqual([["a@x.com"]], rows)
        self.assertEqual([["pa"]], roles_per_row)

    def test_roles_column_removed_from_output(self):
        cols, rows, roles_per_row = extract_roles_per_row(
            ["email", "roles"], [["a@x.com", "mo"]]
        )
        self.assertEqual(["email"], cols)
        self.assertEqual([["a@x.com"]], rows)
        self.assertEqual([["mo", "pa"]], roles_per_row)

    def test_empty_role_cell_gives_participant_only(self):
        _, _, roles_per_row = extract_roles_per_row(
            ["email", "roles"], [["a@x.com", ""]]
        )
        self.assertEqual([["pa"]], roles_per_row)

    def test_participant_always_included_even_if_specified(self):
        _, _, roles_per_row = extract_roles_per_row(
            ["email", "roles"], [["a@x.com", "pa"]]
        )
        self.assertEqual([["pa"]], roles_per_row)

    def test_multiple_roles_comma_separated_and_sorted(self):
        _, _, roles_per_row = extract_roles_per_row(
            ["email", "roles"], [["a@x.com", "pv,mo"]]
        )
        self.assertEqual([["mo", "pa", "pv"]], roles_per_row)

    def test_roles_column_in_middle(self):
        cols, rows, _ = extract_roles_per_row(
            ["email", "roles", "group"],
            [["a@x.com", "mo", "sw"]],
        )
        self.assertEqual(["email", "group"], cols)
        self.assertEqual([["a@x.com", "sw"]], rows)

    def test_per_row_roles_differ(self):
        _, _, roles_per_row = extract_roles_per_row(
            ["email", "roles"],
            [["a@x.com", "mo"], ["b@x.com", ""], ["c@x.com", "pv"]],
        )
        self.assertEqual([["mo", "pa"], ["pa"], ["pa", "pv"]], roles_per_row)


# ---------------------------------------------------------------------------
# Permission tests
# ---------------------------------------------------------------------------


class ImportInvitesPermissionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org: Organisation = Organisation.objects.create()
        cls.meeting: Meeting = cls.org.meetings.create()
        cls.other_meeting: Meeting = cls.org.meetings.create()

        cls.moderator = cls.org.users.create(username="mod", email="mod@x.com")
        cls.meeting.add_roles(cls.moderator, "mo", "pa")

        cls.participant = cls.org.users.create(username="participant", email="p@x.com")
        cls.meeting.add_roles(cls.participant, "pa")

        cls.other_moderator = cls.org.users.create(
            username="other_mod", email="om@x.com"
        )
        cls.other_meeting.add_roles(cls.other_moderator, "mo", "pa")

    def _post(self, user, meeting=None, content=b"email\nalice@example.com\n"):
        if user is not None:
            self.client.force_login(user)
        f = io.BytesIO(content)
        f.name = "invites.csv"
        return self.client.post(
            URL,
            {"meeting": (meeting or self.meeting).pk, "file": f},
            format="multipart",
        )

    def test_unauthenticated_returns_401(self):
        f = io.BytesIO(b"email\nalice@example.com")
        f.name = "invites.csv"
        response = self.client.post(
            URL, {"meeting": self.meeting.pk, "file": f}, format="multipart"
        )
        self.assertEqual(HTTPStatus.UNAUTHORIZED, response.status_code)

    def test_participant_not_moderator_returns_400(self):
        response = self._post(self.participant)
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_moderator_of_different_meeting_returns_400(self):
        # other_moderator moderates other_meeting, not self.meeting
        response = self._post(self.other_moderator)
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_correct_moderator_returns_200(self):
        response = self._post(self.moderator)
        self.assertEqual(HTTPStatus.OK, response.status_code)

    def test_moderator_can_import_to_their_own_meeting(self):
        response = self._post(self.other_moderator, meeting=self.other_meeting)
        self.assertEqual(HTTPStatus.OK, response.status_code)

    def test_archived_meeting_returns_400(self):
        self.meeting.state = MeetingWf.ARCHIVED
        self.meeting.save()
        try:
            response = self._post(self.moderator)
            self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)
        finally:
            self.meeting.state = MeetingWf.ONGOING
            self.meeting.save()


# ---------------------------------------------------------------------------
# File-format integration tests using real fixture files
# ---------------------------------------------------------------------------


class ImportFileFormatTests(APITestCase):
    """Upload the actual fixture files and verify they are parsed and imported correctly."""

    @classmethod
    def setUpTestData(cls):
        cls.org: Organisation = Organisation.objects.create()
        cls.meeting: Meeting = cls.org.meetings.create()
        cls.moderator = cls.org.users.create(username="mod", email="mod@example.com")
        cls.meeting.add_roles(cls.moderator, "mo", "pa")
        cls.group_sw = cls.meeting.groups.create(groupid="sw")
        cls.group_sabreclub = cls.meeting.groups.create(groupid="sabreclub")

    def setUp(self):
        self.client.force_login(self.moderator)

    def _post_fixture(self, filename: str, dryrun: bool = False) -> dict:
        f = fixture_file(filename)
        data = {"meeting": self.meeting.pk, "file": f}
        if dryrun:
            data["dryrun"] = "true"
        response = self.client.post(URL, data, format="multipart")
        self.assertEqual(
            HTTPStatus.OK, response.status_code, f"{filename}: {response.json()}"
        )
        return response.json()

    def _expected_emails(self):
        return {"vader@betahaus.net", "luke@betahaus.net", "din@betahaus.net"}

    def test_comma_separated_csv(self):
        """Google Docs / generic CSV: comma separator, CRLF, no BOM."""
        data = self._post_fixture("comma_separated.csv")
        self.assertEqual(3, data["invites"]["added"])
        emails = set(
            MeetingInvite.objects.filter(meeting=self.meeting).values_list(
                "user_data__email", flat=True
            )
        )
        self.assertEqual(self._expected_emails(), emails)

    def test_tab_separated_tsv(self):
        """TSV with CRLF line endings (copy-paste from Excel)."""
        data = self._post_fixture("tab_separated.tsv")
        self.assertEqual(3, data["invites"]["added"])

    def test_excel_xlsx(self):
        """Real Excel 2007+ .xlsx file."""
        data = self._post_fixture("excel_like.xlsx")
        self.assertEqual(3, data["invites"]["added"])

    def test_open_document_ods(self):
        """LibreOffice / Google Docs .ods file."""
        data = self._post_fixture("open_document.ods")
        self.assertEqual(3, data["invites"]["added"])

    def test_emails_txt_headerless_list(self):
        """Plain text file with one email per line, no header column."""
        data = self._post_fixture("emails.txt")
        self.assertEqual(3, data["invites"]["added"])

    def test_all_formats_produce_same_invite_emails(self):
        """Every spreadsheet format results in the same 3 unique invites."""
        for filename in (
            "comma_separated.csv",
            "tab_separated.tsv",
            "excel_like.xlsx",
            "open_document.ods",
        ):
            with self.subTest(filename=filename):
                MeetingInvite.objects.filter(meeting=self.meeting).delete()
                data = self._post_fixture(filename)
                self.assertEqual(3, data["invites"]["added"], filename)
                emails = set(
                    MeetingInvite.objects.filter(meeting=self.meeting).values_list(
                        "user_data__email", flat=True
                    )
                )
                self.assertEqual(self._expected_emails(), emails, filename)

    def test_group_annotations_created_from_csv(self):
        """Group annotations are created for rows that have a group column."""
        data = self._post_fixture("comma_separated.csv")
        # vader and luke appear in sabreclub, vader+luke+din in sw
        self.assertGreater(data["annotations"][0]["added"], 0)
        self.assertTrue(
            MeetingGroupAnnotation.objects.filter(meeting_group=self.group_sw).exists()
        )

    def test_group_annotations_created_from_xlsx(self):
        data = self._post_fixture("excel_like.xlsx")
        self.assertGreater(data["annotations"][0]["added"], 0)

    def test_group_annotations_created_from_ods(self):
        data = self._post_fixture("open_document.ods")
        self.assertGreater(data["annotations"][0]["added"], 0)

    def test_dryrun_does_not_persist_for_xlsx(self):
        data = self._post_fixture("excel_like.xlsx", dryrun=True)
        self.assertTrue(data["dryrun"])
        self.assertGreater(data["invites"]["added"], 0)
        self.assertFalse(MeetingInvite.objects.filter(meeting=self.meeting).exists())

    def test_unsupported_binary_rejected(self):
        """Uploading a binary file that is not a spreadsheet must return 400."""
        f = io.BytesIO(b"\x7fELF\x02\x01\x01" + b"\x00" * 100)  # ELF binary header
        f.name = "evil.csv"
        response = self.client.post(
            URL, {"meeting": self.meeting.pk, "file": f}, format="multipart"
        )
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_zip_file_that_is_not_spreadsheet_rejected(self):
        """A ZIP file that is not xlsx or ods must be rejected."""
        buf = io.BytesIO()
        with __import__("zipfile").ZipFile(buf, "w") as zf:
            zf.writestr("malware.py", "import os; os.system('rm -rf /')")
        f = io.BytesIO(buf.getvalue())
        f.name = "notaspreadsheet.zip"
        response = self.client.post(
            URL, {"meeting": self.meeting.pk, "file": f}, format="multipart"
        )
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)


# ---------------------------------------------------------------------------
# Roles-column + empty-row fixture tests
# ---------------------------------------------------------------------------


class ImportRolesWithEmptyRowsTests(APITestCase):
    """
    roles_with_empty_rows.tsv is a CRLF tab-separated file that simulates a
    copy-paste from Excel:
      - header: email, roles, group
      - vader: mo role, sw group
      - (empty row — tabs only)
      - luke: no explicit role (→ participant), sw group
      - (blank line)
      - din: pv role, sw group
      - (whitespace-only row — spaces + tabs)
    """

    @classmethod
    def setUpTestData(cls):
        cls.org: Organisation = Organisation.objects.create()
        cls.meeting: Meeting = cls.org.meetings.create()
        cls.moderator = cls.org.users.create(username="mod", email="mod@x.com")
        cls.meeting.add_roles(cls.moderator, "mo", "pa")
        cls.group_sw = cls.meeting.groups.create(groupid="sw")

    def setUp(self):
        self.client.force_login(self.moderator)

    def _post(self, dryrun: bool = False) -> dict:
        f = fixture_file("roles_with_empty_rows.tsv")
        data = {"meeting": self.meeting.pk, "file": f}
        if dryrun:
            data["dryrun"] = "true"
        response = self.client.post(URL, data, format="multipart")
        self.assertEqual(HTTPStatus.OK, response.status_code, response.json())
        return response.json()

    def test_empty_rows_are_ignored_and_three_invites_created(self):
        data = self._post()
        self.assertEqual(3, data["invites"]["added"])

    def test_vader_gets_moderator_and_participant_roles(self):
        self._post()
        vader = MeetingInvite.objects.get(
            meeting=self.meeting, user_data__email="vader@betahaus.net"
        )
        self.assertEqual(["mo", "pa"], vader.roles)

    def test_luke_gets_only_participant_role(self):
        self._post()
        luke = MeetingInvite.objects.get(
            meeting=self.meeting, user_data__email="luke@betahaus.net"
        )
        self.assertEqual(["pa"], luke.roles)

    def test_din_gets_potential_voter_and_participant_roles(self):
        self._post()
        din = MeetingInvite.objects.get(
            meeting=self.meeting, user_data__email="din@betahaus.net"
        )
        self.assertEqual(["pa", "pv"], din.roles)

    def test_group_annotations_created_for_all_rows(self):
        data = self._post()
        self.assertEqual(3, data["annotations"][0]["added"])
        self.assertEqual(
            3,
            MeetingGroupAnnotation.objects.filter(meeting_group=self.group_sw).count(),
        )

    def test_dryrun_does_not_persist(self):
        data = self._post(dryrun=True)
        self.assertTrue(data["dryrun"])
        self.assertEqual(3, data["invites"]["added"])
        self.assertFalse(MeetingInvite.objects.filter(meeting=self.meeting).exists())


# ---------------------------------------------------------------------------
# Functional / end-to-end tests
# ---------------------------------------------------------------------------


class ImportInvitesFunctionalTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org: Organisation = Organisation.objects.create()
        cls.meeting: Meeting = cls.org.meetings.create()
        cls.moderator = cls.org.users.create(username="mod", email="mod@x.com")
        cls.meeting.add_roles(cls.moderator, "mo", "pa")
        cls.group_board = cls.meeting.groups.create(groupid="board")
        cls.role_chair = cls.meeting.group_roles.create(role_id="chair")

    def setUp(self):
        self.client.force_login(self.moderator)

    def _post(self, content: str | bytes, dryrun: bool = False):
        raw = content if isinstance(content, bytes) else content.encode("utf-8")
        f = io.BytesIO(raw)
        f.name = "invites.csv"
        data = {"meeting": self.meeting.pk, "file": f}
        if dryrun:
            data["dryrun"] = "true"
        return self.client.post(URL, data, format="multipart")

    def test_email_only_creates_invites(self):
        response = self._post("email\nalice@example.com\nbob@example.com\n")
        self.assertEqual(HTTPStatus.OK, response.status_code)
        data = response.json()
        self.assertEqual({"added": 2, "changed": 0, "existed": 0}, data["invites"])
        self.assertEqual([], data["annotations"])

    def test_second_import_reports_existed(self):
        self._post("email\nalice@example.com\n")
        response = self._post("email\nalice@example.com\n")
        data = response.json()
        self.assertEqual({"added": 0, "changed": 0, "existed": 1}, data["invites"])

    def test_dryrun_reports_without_persisting(self):
        response = self._post("email\nalice@example.com\n", dryrun=True)
        data = response.json()
        self.assertTrue(data["dryrun"])
        self.assertEqual(1, data["invites"]["added"])
        self.assertFalse(MeetingInvite.objects.filter(meeting=self.meeting).exists())

    def test_windows_excel_bom_crlf_csv(self):
        """UTF-8 BOM + CRLF: exactly what Windows Excel saves as CSV."""
        content = "email,roles\r\nalice@example.com,mo\r\nbob@example.com,\r\n"
        response = self._post(content.encode("utf-8-sig"))
        self.assertEqual(HTTPStatus.OK, response.status_code)
        alice = MeetingInvite.objects.get(
            meeting=self.meeting, user_data__email="alice@example.com"
        )
        self.assertEqual(["mo", "pa"], alice.roles)

    def test_roles_column_sets_per_row_roles(self):
        response = self._post("email,roles\nalice@example.com,mo\nbob@example.com,\n")
        self.assertEqual(HTTPStatus.OK, response.status_code)
        alice = MeetingInvite.objects.get(
            meeting=self.meeting, user_data__email="alice@example.com"
        )
        bob = MeetingInvite.objects.get(
            meeting=self.meeting, user_data__email="bob@example.com"
        )
        self.assertEqual(["mo", "pa"], alice.roles)
        self.assertEqual(["pa"], bob.roles)

    def test_no_roles_column_defaults_to_participant(self):
        self._post("email\nalice@example.com\n")
        invite = MeetingInvite.objects.get(
            meeting=self.meeting, user_data__email="alice@example.com"
        )
        self.assertEqual(["pa"], invite.roles)

    def test_group_annotation_stored_on_pending_invite(self):
        response = self._post("email\tgroup\nalice@example.com\tboard\n")
        self.assertEqual(HTTPStatus.OK, response.status_code)
        data = response.json()
        self.assertEqual(1, data["annotations"][0]["added"])
        alice = MeetingInvite.objects.get(
            meeting=self.meeting, user_data__email="alice@example.com"
        )
        self.assertTrue(
            alice.group_annotations.filter(meeting_group=self.group_board).exists()
        )

    def test_group_role_annotation_stored(self):
        self._post("email\tgroup\tgrouprole\nalice@example.com\tboard\tchair\n")
        alice = MeetingInvite.objects.get(
            meeting=self.meeting, user_data__email="alice@example.com"
        )
        ann = alice.group_annotations.get(meeting_group=self.group_board)
        self.assertEqual(self.role_chair, ann.group_role)

    def test_unknown_group_returns_400(self):
        response = self._post("email\tgroup\nalice@example.com\tunknown_group\n")
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_moderator_lockout_protection(self):
        existing = self.meeting.invites.create(
            user_data={"email": "mod@x.com"}, roles=["mo", "pa"]
        )
        existing.accept(self.moderator)
        existing.save()
        response = self._post("email\nmod@x.com\n")
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_invalid_email_format_returns_400(self):
        response = self._post("email\nnot-an-email\n")
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_empty_file_returns_400(self):
        response = self._post("")
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_duplicate_column_returns_400(self):
        response = self._post("email,email\nalice@example.com,alice@example.com\n")
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)


# ---------------------------------------------------------------------------
# User error message tests — bad fixture files
# ---------------------------------------------------------------------------


class ImportInvitesBadFileTests(APITestCase):
    """
    Verify that common user mistakes produce HTTP 400 responses with
    error messages that make sense to a non-technical user.

    Each test uses a fixture file that represents a realistic mistake.
    """

    @classmethod
    def setUpTestData(cls):
        cls.org: Organisation = Organisation.objects.create()
        cls.meeting: Meeting = cls.org.meetings.create()
        cls.moderator = cls.org.users.create(username="mod", email="mod@x.com")
        cls.meeting.add_roles(cls.moderator, "mo", "pa")
        # Groups referenced in the semicolon fixture file
        cls.meeting.groups.create(groupid="sw")

    def setUp(self):
        self.client.force_login(self.moderator)

    def _post_fixture(self, filename: str):
        f = fixture_file(filename)
        return self.client.post(
            URL,
            {"meeting": self.meeting.pk, "file": f},
            format="multipart",
        )

    def _error_text(self, response) -> str:
        """Return the full error text from the response, lowercased for easy assertions."""
        return str(response.json()).lower()

    # --- bad_email_typo.csv ---
    # Content: email column with 'notanemail' on row 2 among otherwise valid addresses.
    # Expectation: 400 with a message pointing to the offending row and the column name.

    def test_bad_email_typo_returns_400(self):
        response = self._post_fixture("bad_email_typo.csv")
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_bad_email_typo_message_mentions_row(self):
        response = self._post_fixture("bad_email_typo.csv")
        error = self._error_text(response)
        # Should tell the user which row is bad, not just that something failed
        self.assertIn("row", error)

    def test_bad_email_typo_message_mentions_email_column(self):
        response = self._post_fixture("bad_email_typo.csv")
        error = self._error_text(response)
        self.assertIn("email", error)

    # --- bad_column_typo.csv ---
    # Content: column header is 'e-mail' instead of 'email'.
    # Expectation: 400 with a message saying the column name is not valid.

    def test_bad_column_typo_returns_400(self):
        response = self._post_fixture("bad_column_typo.csv")
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_bad_column_typo_message_mentions_the_bad_column(self):
        response = self._post_fixture("bad_column_typo.csv")
        error = self._error_text(response)
        # The message should name the unknown column so the user knows what to fix
        self.assertIn("e-mail", error)

    def test_bad_column_typo_message_says_not_valid(self):
        response = self._post_fixture("bad_column_typo.csv")
        error = self._error_text(response)
        self.assertIn("not a valid column", error)

    # --- bad_grouprole_without_group.csv ---
    # Content: has 'grouprole' column but is missing the required 'group' column.
    # Expectation: 400 with an explanation that grouprole requires group.

    def test_bad_grouprole_without_group_returns_400(self):
        response = self._post_fixture("bad_grouprole_without_group.csv")
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_bad_grouprole_without_group_message_is_descriptive(self):
        response = self._post_fixture("bad_grouprole_without_group.csv")
        error = self._error_text(response)
        # Should explain that grouprole needs the group column
        self.assertIn("group", error)
        self.assertIn("grouprole", error)

    # --- bad_duplicate_email.csv ---
    # Content: the same email address appears on two separate rows.
    # Expectation: 400 with a message about duplicate rows.

    def test_bad_duplicate_email_returns_400(self):
        response = self._post_fixture("bad_duplicate_email.csv")
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_bad_duplicate_email_message_mentions_duplicates(self):
        response = self._post_fixture("bad_duplicate_email.csv")
        error = self._error_text(response)
        self.assertIn("duplicate", error)

    # --- bad_semicolon_separator.csv ---
    # Content: semicolon-separated (European Excel default — Swedish/EU users get this by default).
    # Our parser detects semicolons and handles them correctly, so this should succeed.

    def test_semicolon_separated_is_accepted(self):
        """European Excel CSV (semicolon separator) must work — it is the normal format for Swedish users."""
        response = self._post_fixture("bad_semicolon_separator.csv")
        self.assertEqual(HTTPStatus.OK, response.status_code)
        self.assertEqual(2, response.json()["invites"]["added"])

    # --- bad_wrong_column_order.csv ---
    # Content: 'grouprole' appears without 'group' directly to its left (roles column is in between).
    # Expectation: 400 explaining that grouprole requires group as the preceding column.

    def test_bad_wrong_column_order_returns_400(self):
        response = self._post_fixture("bad_wrong_column_order.csv")
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_bad_wrong_column_order_message_is_descriptive(self):
        response = self._post_fixture("bad_wrong_column_order.csv")
        error = self._error_text(response)
        self.assertIn("group", error)
        self.assertIn("grouprole", error)

    # --- bad_header_only.csv ---
    # Content: only a header row ('email'), no data rows at all.
    # Expectation: 400 with a message saying there are no data rows.

    def test_bad_header_only_returns_400(self):
        response = self._post_fixture("bad_header_only.csv")
        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status_code)

    def test_bad_header_only_message_mentions_no_data(self):
        response = self._post_fixture("bad_header_only.csv")
        error = self._error_text(response)
        self.assertIn("no data", error)
