from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile

from voteit.meeting.roles import ROLE_PARTICIPANT

# Mostly for doctests...
_PARTICIPANT = str(ROLE_PARTICIPANT)

# Security limits
MAX_UPLOAD_BYTES = (
    2 * 1024 * 1024
)  # 2 MB — rejects unexpectedly large files before parsing
MAX_ROWS = 1000  # Stop parsing after this many data rows
_MAX_XML_ENTRY_BYTES = 5 * 1024 * 1024  # 5 MB per XML entry — guards against zip bombs

# Magic bytes for ZIP-based formats (xlsx and ods are both ZIP archives)
_ZIP_MAGIC = b"PK\x03\x04"

# ODS mimetype string (stored uncompressed in the ZIP)
_ODS_MIMETYPE = "application/vnd.oasis.opendocument.spreadsheet"

# XML namespaces used in ODS content.xml
_ODS_TABLE_NS = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
_ODS_TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"

# Column-letter to 0-based index (A→0, B→1, …, AA→26, …)
_COL_REF_RE = re.compile(r"([A-Z]+)(\d+)")


def _col_letters_to_idx(letters: str) -> int:
    result = 0
    for ch in letters:
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def detect_and_parse_file(raw: bytes) -> tuple[list[str], list[list[str]]]:
    """
    Detect file type by content (not filename or extension) and return (columns, rows).

    Supported formats:
    - XLSX (Excel 2007+) — detected by ZIP magic bytes + xl/ content
    - ODS (LibreOffice/Google Docs) — detected by ZIP magic bytes + ODS mimetype
    - CSV / TSV (plain UTF-8 text) — fallback for non-ZIP files
    - Headerless email list — single-column text file without a column header

    Raises ValueError for unrecognised or unsupported binary formats.
    """
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"File is too large ({len(raw) // 1024} KB). Maximum allowed size is "
            f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )
    if raw[:4] == _ZIP_MAGIC:
        return _parse_zip_spreadsheet(raw)
    # Treat as UTF-8 text — reject non-decodable binaries
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError(
            "Unsupported file format. Upload an Excel file (.xlsx), "
            "an ODS spreadsheet, or a UTF-8 CSV/TSV file."
        )
    return parse_invite_file(content)


# ---------------------------------------------------------------------------
# ZIP-based spreadsheet dispatcher
# ---------------------------------------------------------------------------


def _safe_zip_read(zf: zipfile.ZipFile, name: str) -> bytes:
    """Read a ZIP entry, raising ValueError if its uncompressed size exceeds the limit."""
    info = zf.getinfo(name)
    if info.file_size > _MAX_XML_ENTRY_BYTES:
        raise ValueError(
            f"The file contains an entry that is too large to process ({name})."
        )
    return zf.read(name)


def _parse_zip_spreadsheet(raw: bytes) -> tuple[list[str], list[list[str]]]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = set(zf.namelist())
            # ODS: has a 'mimetype' entry with the ODS content type
            if "mimetype" in names:
                mime = _safe_zip_read(zf, "mimetype").decode("utf-8").strip()
                if mime == _ODS_MIMETYPE:
                    return _parse_ods_zip(zf)
                raise ValueError(
                    f"Unsupported ODF format '{mime}'. Only spreadsheets (.ods) are supported."
                )
            # XLSX: has xl/ directory and [Content_Types].xml
            if "[Content_Types].xml" in names and any(
                n.startswith("xl/") for n in names
            ):
                return _parse_xlsx_zip(zf)
            raise ValueError(
                "Unrecognised ZIP-based format. Upload an Excel (.xlsx) or ODS (.ods) file."
            )
    except zipfile.BadZipFile:
        raise ValueError(
            "The file appears to be corrupt or is not a valid spreadsheet."
        )


# ---------------------------------------------------------------------------
# XLSX parser (stdlib only — no openpyxl required)
# ---------------------------------------------------------------------------


def _parse_xlsx_zip(zf: zipfile.ZipFile) -> tuple[list[str], list[list[str]]]:
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

    # Shared strings table
    shared_strings: list[str] = []
    if "xl/sharedStrings.xml" in zf.namelist():
        ss_root = ET.fromstring(_safe_zip_read(zf, "xl/sharedStrings.xml"))
        for si in ss_root.findall("x:si", ns):
            # Concatenate all <t> text (handles rich text runs)
            text = "".join(t.text or "" for t in si.findall(".//x:t", ns))
            shared_strings.append(text)

    # First worksheet
    sheet_names = sorted(
        n for n in zf.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n)
    )
    if not sheet_names:
        raise ValueError("No worksheet found in the Excel file.")

    sheet_root = ET.fromstring(_safe_zip_read(zf, sheet_names[0]))
    raw_rows: dict[int, dict[int, str]] = {}  # {row_idx: {col_idx: value}}

    for cell in sheet_root.findall(".//x:c", ns):
        ref = cell.get("r", "")
        m = _COL_REF_RE.match(ref)
        if not m:
            continue
        col_idx = _col_letters_to_idx(m.group(1))
        row_idx = int(m.group(2)) - 1  # 0-based
        if row_idx > MAX_ROWS:  # +1 for header row
            continue
        v_elem = cell.find("x:v", ns)
        if v_elem is None or v_elem.text is None:
            continue
        cell_type = cell.get("t", "")
        if cell_type == "s":
            value = shared_strings[int(v_elem.text)]
        elif cell_type == "inlineStr":
            is_elem = cell.find("x:is/x:t", ns)
            value = is_elem.text if is_elem is not None else ""
        else:
            value = v_elem.text
        raw_rows.setdefault(row_idx, {})[col_idx] = value

    return _dict_rows_to_columns_rows(raw_rows)


# ---------------------------------------------------------------------------
# ODS parser (stdlib only — no odfpy required)
# ---------------------------------------------------------------------------


def _parse_ods_zip(zf: zipfile.ZipFile) -> tuple[list[str], list[list[str]]]:
    root = ET.fromstring(_safe_zip_read(zf, "content.xml").decode("utf-8"))
    sheet = root.find(f".//{{{_ODS_TABLE_NS}}}table")
    if sheet is None:
        raise ValueError("No sheet found in the ODS file.")

    raw_rows: dict[int, dict[int, str]] = {}
    row_idx = 0

    for row_elem in sheet.findall(f"{{{_ODS_TABLE_NS}}}table-row"):
        col_idx = 0
        has_data = False
        for cell_elem in row_elem.findall(f"{{{_ODS_TABLE_NS}}}table-cell"):
            col_repeat = int(
                cell_elem.get(f"{{{_ODS_TABLE_NS}}}number-columns-repeated", 1)
            )
            p = cell_elem.find(f".//{{{_ODS_TEXT_NS}}}p")
            value = p.text if p is not None else None
            if value is None and col_repeat > 20:
                # Trailing "fill to end of spreadsheet" block — stop this row
                break
            if value is not None:
                has_data = True
                for _ in range(col_repeat):
                    raw_rows.setdefault(row_idx, {})[col_idx] = value
                    col_idx += 1
            else:
                col_idx += col_repeat
        if has_data:
            row_idx += 1
            if row_idx > MAX_ROWS:  # +1 for header row already consumed
                break
        # If row had no data and row_repeat is large, skip the whole block

    return _dict_rows_to_columns_rows(raw_rows)


# ---------------------------------------------------------------------------
# Shared row-dict → (columns, rows) converter
# ---------------------------------------------------------------------------


def _dict_rows_to_columns_rows(
    raw_rows: dict[int, dict[int, str]],
) -> tuple[list[str], list[list[str]]]:
    if not raw_rows:
        raise ValueError("The spreadsheet contains no data.")

    sorted_row_indices = sorted(raw_rows)
    header_dict = raw_rows[sorted_row_indices[0]]
    n_cols = max(header_dict) + 1 if header_dict else 0

    columns = [(header_dict.get(i) or "").strip().lower() for i in range(n_cols)]
    # Drop trailing empty column headers (e.g. from ODS files with extra columns)
    while columns and not columns[-1]:
        columns.pop()
    if not columns:
        raise ValueError("The spreadsheet header row is empty.")

    n_cols = len(columns)
    rows = []
    for ri in sorted_row_indices[1:]:
        row_dict = raw_rows[ri]
        row = [(row_dict.get(i) or "").strip() for i in range(n_cols)]
        if any(row):
            rows.append(row)

    return columns, rows


# ---------------------------------------------------------------------------
# Text file parser (CSV / TSV / headerless email list)
# ---------------------------------------------------------------------------


def parse_invite_file(content: str) -> tuple[list[str], list[list[str]]]:
    """
    Parse CSV or TSV string. First row = column headers unless it looks like an email
    list without headers (no recognisable column name in the first cell), in which case
    'email' is prepended automatically.

    Auto-detects separator (tab or comma). Handles CRLF and LF line endings.

    >>> parse_invite_file("email\\tgroup\\nalice@x.com\\tsw")
    (['email', 'group'], [['alice@x.com', 'sw']])

    >>> parse_invite_file("email,group\\nalice@x.com,sw\\n\\n")
    (['email', 'group'], [['alice@x.com', 'sw']])

    >>> parse_invite_file("email;group\\nalice@x.com;sw")
    (['email', 'group'], [['alice@x.com', 'sw']])

    >>> parse_invite_file("alice@x.com\\nbob@x.com")
    (['email'], [['alice@x.com'], ['bob@x.com']])

    >>> parse_invite_file("")
    Traceback (most recent call last):
    ...
    ValueError: File is empty
    """
    lines = [line for line in content.splitlines() if line.strip()]
    if not lines:
        raise ValueError("File is empty")

    if "\t" in lines[0]:
        sep = "\t"
    elif ";" in lines[0]:
        sep = ";"
    else:
        sep = ","
    first_cells = [c.strip() for c in lines[0].split(sep)]

    # Detect headerless single-column email list (first cell contains '@')
    if len(first_cells) == 1 and "@" in first_cells[0]:
        columns = ["email"]
        rows = [[c.strip()] for line in lines for c in [line.strip()] if c]
        return columns, rows

    columns = [c.lower() for c in first_cells]
    rows = [[cell.strip() for cell in line.split(sep)] for line in lines[1:]]
    return columns, rows


# ---------------------------------------------------------------------------
# Role extraction
# ---------------------------------------------------------------------------


def extract_roles_per_row(
    columns: list[str], rows: list[list[str]]
) -> tuple[list[str], list[list[str]], list[list[str]]]:
    """
    Remove the 'roles' column and return per-row roles.
    PARTICIPANT is always included implicitly.

    Returns (columns_without_roles, rows_without_roles, roles_per_row).

    >>> extract_roles_per_row(['email', 'roles'], [['a@x.com', 'mo'], ['b@x.com', '']])
    (['email'], [['a@x.com'], ['b@x.com']], [['mo', 'pa'], ['pa']])

    >>> extract_roles_per_row(['email'], [['a@x.com']])
    (['email'], [['a@x.com']], [['pa']])
    """
    if "roles" not in columns:
        return columns, rows, [[_PARTICIPANT]] * len(rows)

    role_idx = columns.index("roles")
    new_columns = [c for c in columns if c != "roles"]
    roles_per_row = []
    new_rows = []
    for row in rows:
        raw = row[role_idx] if role_idx < len(row) else ""
        extra = {r.strip() for r in raw.split(",") if r.strip()}
        roles_per_row.append(sorted({_PARTICIPANT} | extra))
        new_rows.append([v for i, v in enumerate(row) if i != role_idx])
    return new_columns, new_rows, roles_per_row
