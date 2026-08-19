from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management import BaseCommand

from voteit.core.user_merger import UserMerger


class Command(BaseCommand):
    help = "Merge a source user into a target user, reassigning all related data."

    def add_arguments(self, parser):
        parser.add_argument(
            "source_pk",
            type=int,
            help="PK of the source user (will be deactivated after merge)",
        )
        parser.add_argument(
            "target_pk",
            type=int,
            help="PK of the target user (will receive all data)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Simulate the merge without making any changes",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        source_pk = options["source_pk"]
        target_pk = options["target_pk"]
        dry_run = options["dry_run"]

        try:
            source = User.objects.select_related("organisation").get(pk=source_pk)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Source user pk={source_pk} not found"))
            return

        try:
            target = User.objects.select_related("organisation").get(pk=target_pk)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Target user pk={target_pk} not found"))
            return

        self.stdout.write(f"Source: {source} (pk={source.pk})")
        self.stdout.write(f"Target: {target} (pk={target.pk})")
        if dry_run:
            self.stdout.write(
                self.style.WARNING("=== DRY RUN — no changes will be made ===")
            )

        merger = UserMerger(source=source, target=target, dry_run=dry_run)
        try:
            log = merger.run()
        except ValueError as e:
            self.stderr.write(self.style.ERROR(f"Validation error: {e}"))
            return

        self.stdout.write("")
        if log.moved:
            self.stdout.write("=== Moved ===")
            for msg in log.moved:
                self.stdout.write(f"  + {msg}")

        if log.merged_roles:
            self.stdout.write("")
            self.stdout.write("=== Role merges ===")
            for msg in log.merged_roles:
                self.stdout.write(f"  ~ {msg}")

        if log.deleted:
            self.stdout.write("")
            self.stdout.write("=== Deleted (transient) ===")
            for msg in log.deleted:
                self.stdout.write(f"  - {msg}")

        if log.skipped:
            self.stdout.write("")
            self.stdout.write("=== Skipped (conflicts) ===")
            for msg in log.skipped:
                self.stdout.write(self.style.WARNING(f"  ! {msg}"))

        self.stdout.write("")
        summary = (
            f"Summary: {len(log.moved)} moved, "
            f"{len(log.merged_roles)} role merges, "
            f"{len(log.deleted)} deleted, "
            f"{len(log.skipped)} skipped"
        )
        if dry_run:
            self.stdout.write(self.style.WARNING(summary + " (DRY RUN)"))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
