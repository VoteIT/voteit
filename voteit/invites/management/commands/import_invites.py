from __future__ import annotations

import sys
from itertools import groupby

from django.core.management import BaseCommand
from django.core.management import CommandError
from django.db import transaction

from voteit.invites.rest_api.import_utils import detect_and_parse_file
from voteit.invites.rest_api.import_utils import extract_roles_per_row
from voteit.invites.schemas import RowColInvitesBaseSchema
from voteit.invites.schemas import schema_context
from voteit.invites.utils import get_invite_adapter_registry
from voteit.meeting.models import Meeting


class Command(BaseCommand):
    help = (
        "Import invites (and optional annotations) into a meeting from a file or stdin. "
        "Supports XLSX, ODS, CSV, TSV, and plain email lists. "
        "Roles are read from a 'roles' column; rows without one default to PARTICIPANT. "
        "Annotation columns (group, grouprole) are applied after invite creation."
    )

    def add_arguments(self, parser):
        parser.add_argument("-m", required=True, help="Meeting PK")
        parser.add_argument("-f", help="Path to input file (default: stdin)")
        parser.add_argument(
            "--dryrun",
            action="store_true",
            default=False,
            help="Validate and report without saving",
        )

    def handle(self, *args, **options):
        meeting: Meeting = Meeting.objects.get(pk=options["m"])

        raw = self._read_bytes(options.get("f"))
        try:
            columns, rows = detect_and_parse_file(raw)
        except ValueError as exc:
            raise CommandError(str(exc))

        if not rows:
            raise CommandError("The file contains no data rows.")

        columns, rows, roles_per_row = extract_roles_per_row(columns, rows)

        try:
            with schema_context(limit=None):
                validated = RowColInvitesBaseSchema(columns=columns, rows=rows)
        except Exception as exc:
            raise CommandError(str(exc))

        columns = validated.columns
        rows = validated.rows

        reg = get_invite_adapter_registry()
        total_added = total_changed = total_existed = 0

        with transaction.atomic(durable=True):
            indexed = sorted(enumerate(rows), key=lambda t: roles_per_row[t[0]])
            for role_combo, group_iter in groupby(
                indexed, key=lambda t: roles_per_row[t[0]]
            ):
                group_rows = [row for _, row in group_iter]
                items = list(reg.build_ud_query_seq(columns, group_rows))
                if not items:
                    continue
                result = meeting.invites.create_or_update_mixed(
                    data=items, roles=role_combo, meeting=meeting
                )
                total_added += result.added
                total_changed += result.changed
                total_existed += result.existed

            self.stdout.write(
                self.style.SUCCESS(
                    f"Invites — added: {total_added}  changed: {total_changed}  existed: {total_existed}"
                )
            )

            if reg.get_annotations(columns):
                try:
                    reg.run_validators(columns=columns, rows=rows, meeting=meeting)
                except ValueError as exc:
                    raise CommandError(str(exc))
                for ann_result in reg.run_annotations(
                    columns=columns,
                    rows=rows,
                    invites_qs=meeting.invites.all(),
                    meeting=meeting,
                ):
                    if ann_result:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Annotation '{ann_result.name}' — "
                                f"added: {ann_result.added}  "
                                f"changed: {ann_result.changed}  "
                                f"existed: {ann_result.existed}"
                            )
                        )

            if options["dryrun"]:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("-- DRY RUN — transaction rolled back, nothing saved"))

    def _read_bytes(self, filepath: str | None) -> bytes:
        if filepath:
            try:
                with open(filepath, "rb") as f:
                    return f.read()
            except OSError as exc:
                raise CommandError(f"Cannot read file: {exc}")
        if sys.stdin.isatty():
            raise CommandError("No file specified and no data on stdin.")
        return sys.stdin.buffer.read()
