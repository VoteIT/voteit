from django.core.management.base import BaseCommand

from voteit.stats.archive import archive_month
from voteit.stats.archive import cutoff_for
from voteit.stats.archive import months_before


class Command(BaseCommand):
    help = (
        "Save stats from auditlog entries older than --months, archive the entries "
        "as JSON lines without personal data and delete them. One calendar month at a time. "
        "Does nothing without --commit."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--months",
            type=int,
            default=18,
            help="Keep this many whole months, plus the current one. Default 18.",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Archive and delete. Without it, only show what would be archived.",
        )
        parser.add_argument(
            "--keep-entries",
            action="store_true",
            help=(
                "Save stats and archive files but don't delete the entries. "
                "Existing stats are recomputed, so this can be rerun."
            ),
        )

    def handle(self, *, months: int, commit: bool, keep_entries: bool, **options):
        dry_run = not commit
        if months < 0:
            self.stderr.write("--months can't be negative")
            return
        cutoff = cutoff_for(months)
        todo = months_before(cutoff)
        self.stdout.write(
            f"{len(todo)} month(s) before {cutoff:%Y-%m-%d}"
            + (" (dry run, use --commit to archive)" if dry_run else "")
        )
        for start in todo:
            result = archive_month(start, dry_run=dry_run, keep_entries=keep_entries)
            if dry_run:
                self.stdout.write(f"{start:%Y-%m}: {result.entries} entries")
                continue
            done = "kept" if keep_entries else "deleted"
            self.stdout.write(
                f"{start:%Y-%m}: {result.entries} entries archived to {result.filename} "
                f"and {done}, "
                f"stats for {result.org_months} org month(s), {result.org_years} "
                f"org year(s), {result.meetings} meeting(s)"
            )
