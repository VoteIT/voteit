from __future__ import annotations

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand


class Command(BaseCommand):
    help = "Delete user image files from MEDIA_ROOT that are no longer referenced by any user."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Report files that would be deleted without removing them",
        )
        parser.add_argument(
            "--org",
            type=int,
            metavar="ORG_ID",
            help="Limit scan to a single organisation directory (org_<ORG_ID>)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        org_filter = options["org"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("=== DRY RUN — no files will be deleted ===")
            )

        # Build the set of relative paths currently stored in the database.
        User = get_user_model()
        referenced = set(
            User.objects.exclude(image="")
            .exclude(image=None)
            .values_list("image", flat=True)
        )

        media_root = settings.MEDIA_ROOT
        deleted = 0
        total = 0

        # Only look inside org_*/images/ directories so we never touch
        # unrelated files that may live elsewhere under MEDIA_ROOT.
        try:
            entries = os.scandir(media_root)
        except FileNotFoundError:
            self.stdout.write("MEDIA_ROOT does not exist — nothing to do.")
            return

        with entries:
            for org_dir in entries:
                if not org_dir.is_dir():
                    continue
                if not org_dir.name.startswith("org_"):
                    continue
                if org_filter is not None:
                    if org_dir.name != f"org_{org_filter}":
                        continue

                images_dir = os.path.join(org_dir.path, "images")
                if not os.path.isdir(images_dir):
                    continue

                for entry in os.scandir(images_dir):
                    if not entry.is_file():
                        continue
                    total += 1
                    # Relative path as stored in the FileField
                    rel = os.path.join(org_dir.name, "images", entry.name)
                    if rel in referenced:
                        continue

                    if dry_run:
                        self.stdout.write(f"  would delete  {rel}")
                    else:
                        os.remove(entry.path)
                        self.stdout.write(f"  deleted  {rel}")
                    deleted += 1

        label = "would delete" if dry_run else "deleted"
        summary = f"{label} {deleted} of {total} file(s)"
        if dry_run:
            self.stdout.write(self.style.WARNING(summary + " (DRY RUN)"))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
