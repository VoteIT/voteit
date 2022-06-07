from __future__ import annotations

import os
import traceback

from django.contrib.auth import get_user_model
from django.core.management import BaseCommand
from django.db import DEFAULT_DB_ALIAS
from django.db import transaction
from dolly.core import Importer


class Command(BaseCommand):
    help = "Import all organisation related things. Create a new organisation or merge with an existing."

    def add_arguments(self, parser):
        parser.add_argument(
            "filename",
            help="Input file to read from",
        )
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help='Nominates a specific database to load fixtures into. Defaults to the "default" database.',
        )
        parser.add_argument(
            "--dry-run",
            default=False,
            action="store_true",
            help="Do nothing, just report",
        )
        parser.add_argument(
            "--merge",
            help="Merge with this organisation pk. The organisation object itself won't be imported.",
        )
        # parser.add_argument(
        #     "-o",
        #     help="Output filemap",
        # )
        parser.add_argument(
            "--reuse-userid",
            help="Reuse organisation users with the same userid. "
            "It only works on existing organisations with --merge.",
            default=False,
            action="store_true",
        )

    def handle(self, *args, **options):
        rel_fn = options["filename"]
        reuse_userid = options["reuse_userid"]
        merge_org = options["merge"]
        if not merge_org and reuse_userid:
            raise ValueError("reuse userid can only be specified together with merge.")
        dry_run = options["dry_run"]
        # quiet = options["quiet"]
        if dry_run:  # and not quiet:
            print("!! Dry run - nothing will be saved !!")
        filename = os.path.join(os.getcwd(), rel_fn)
        importer = Importer.from_filename(filename)
        importer.print_log = True
        # There are some reverse dependencies here, but they're for attributes we don't really need to care about
        # so we'll simply ignore them to solve the conflict.
        # This will destroy data, but active list or speaker should never be imported anyway.
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList
        from voteit.organisation.models import Organisation

        importer.add_clear_attrs(SpeakerListSystem, "active_list")
        importer.add_clear_attrs(SpeakerList, "current")
        importer.add_clear_attrs(Organisation, "author", "last_modified_by")

        if merge_org:
            from voteit.organisation.models import Organisation

            assert len(importer.data[Organisation]) == 1
            deserialized_org = next(iter(importer.data[Organisation]))
            org = Organisation.objects.get(pk=merge_org)
            importer.replace_deserialized_object(deserialized_org, org)
            importer.add_log(
                mod=Organisation,
                act="merge",
                msg=f"Replacing organisation from import with organisation we want to merge with",
            )
            User = get_user_model()
            # Since the exclude operation is a bit more complex than just keywords we'll do it semi-manual here.
            # Even if this is slower, we make sure that we'll never match users outside of this org.
            exclude_qs = User.objects.all().exclude(organisation=org).distinct()
            attrs = ["username", "email"]
            if reuse_userid:
                attrs.append("userid")
            for attr in attrs:
                round_qs = importer.match_and_update(User, attr, exclude_qs=exclude_qs)
                exclude_qs = round_qs | exclude_qs
        try:
            with transaction.atomic(durable=True):
                importer()
                if dry_run:
                    print("!! DRY-RUN - nothing saved !!")
                    transaction.set_rollback(True)
        except Exception as exc:
            traceback.print_exc()
        else:
            print("DONE!")
