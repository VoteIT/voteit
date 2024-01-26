import sys

from django.contrib.auth import get_user_model
from django.core.serializers.base import DeserializedObject
from django.db import transaction

from voteit.core.importers.base import BaseImport
from voteit.core.importers.base import BaseImporter
from voteit.core.utils import get_model_shortname
from voteit.organisation.models import Organisation


User = get_user_model()


class OrganisationImport(BaseImport):
    name = settings_key = "organisation"


class OrganisationImporter(BaseImporter):
    import_class = OrganisationImport

    def run(self, dry=False, existing_organisation_pk=None, reuse_userid=False):
        # We need to muck about with all objects so keeping them in memory (or later in a temp file) is required :/
        # Create new organisation if existing_organisation_pk isn't specified
        if existing_organisation_pk:
            organisation = Organisation.objects.get(pk=existing_organisation_pk)
        else:
            organisation = None
        deserialized_organisation = None
        email_to_import_pk = {}
        username_to_import_pk = {}  # In case of duplicate run!
        userid_to_import_pk = {}

        for deserialized in self.load_objects():
            shortname = get_model_shortname(deserialized.object)
            if shortname == "organisation":
                if deserialized_organisation is not None:
                    sys.exit("Multiple organisations found in import file")
                deserialized_organisation = deserialized
                # Change organisation pointer
                if organisation is None:
                    self.add_obj_to_handle(deserialized)
                else:
                    self.objects_to_handle["organisation"] = {
                        deserialized.object.pk: organisation
                    }
            elif shortname == "user":
                if deserialized.object.email:
                    deserialized.object.email = deserialized.object.email.lower()
                    if deserialized.object.email in email_to_import_pk:
                        raise ValueError(
                            f"Duplicate email address: {deserialized.object.email}"
                        )
                    email_to_import_pk[deserialized.object.email] = (
                        deserialized.object.pk
                    )
                # username
                if deserialized.object.username in username_to_import_pk:
                    raise ValueError(
                        f"Duplicate username in import: {deserialized.object.username}"
                    )
                username_to_import_pk[deserialized.object.username] = (
                    deserialized.object.pk
                )
                # userid
                if deserialized.object.userid in userid_to_import_pk:
                    raise ValueError(
                        f"Duplicate userid in import: {deserialized.object.userid}"
                    )
                userid_to_import_pk[deserialized.object.userid] = deserialized.object.pk
                # Thumbs up
                self.add_obj_to_handle(deserialized)
            else:
                # All other objects
                self.add_obj_to_handle(deserialized)

        import_order = [
            "organisation",
            "user",
            "meeting",
            "agenda_item",
            "speaker_system",
            "speaker_list",
            "meeting_group",
            "electoral_register",
            "voter_weight",
            "proposal",  # Before diff!
            "pnsystem",
            "poll",
            "vote",
        ]
        # FIXME: Figure out ordering from relations that need to be replaced instead.

        with transaction.atomic():
            if organisation is None:
                self.save_obj(deserialized_organisation)
                organisation = deserialized_organisation.object

            # If users already exist within the db, we'll replace the import objects and point them to the real user
            existing_qs = User.objects.filter(
                email__in=email_to_import_pk.keys(), organisation=organisation
            )
            matched_existing_emails = existing_qs.count()
            for user in existing_qs:
                self.objects_to_handle["user"][email_to_import_pk[user.email]] = user
            existing_qs_username = User.objects.filter(
                username__in=username_to_import_pk.keys(), organisation=organisation
            ).exclude(pk__in=existing_qs)
            matched_existing_username = existing_qs_username.count()
            for user in existing_qs_username:
                self.objects_to_handle["user"][
                    username_to_import_pk[user.username]
                ] = user
            matched_existing_userid = 0
            if reuse_userid:
                existing_qs_userid = User.objects.filter(
                    userid__in=userid_to_import_pk.keys(), organisation=organisation
                ).exclude(pk__in=existing_qs_username)
                for user in existing_qs_userid:
                    self.objects_to_handle["user"][
                        userid_to_import_pk[user.userid]
                    ] = user
                matched_existing_userid = existing_qs_userid.count()
            print(
                f"Found {matched_existing_emails} users via email and {matched_existing_username} via username. "
            )
            if reuse_userid:
                print(
                    f"Warning: Reusing {matched_existing_userid} form userid. "
                    f"This is not a good idea if you have existing data!"
                )
            print(
                f"Will remap to those users instead of creating new ones. "
                f"Total users to handle: {len(self.objects_to_handle['user'])}"
            )

            # Handle users with the other importer?
            [
                import_order.append(x)
                for x in self.objects_to_handle
                if x not in import_order
            ]
            import_order.remove("organisation")  # Should not be touched

            for name in import_order:
                try:
                    items = self.objects_to_handle[name]
                except KeyError:
                    print(f"{name} not found in objects_to_handle.")
                    continue
                print(f"Handling {len(items)} {name}")
                for deserialized in items.values():
                    if isinstance(deserialized, DeserializedObject):
                        # Skip handling things we fetched from the database
                        # if deserialized.object.name == "poll":
                        #    breakpoint()
                        self.update_special_fields(deserialized)
                        try:
                            self.save_obj(deserialized)
                        except Exception as exc:
                            breakpoint()
                            pass
                    else:
                        # We don't need to handle regular objects right...?
                        pass
            self.update_deferred()
            if dry:
                print("== Dry-run - aborting transaction ==")
                transaction.set_rollback(True)

        self.stream.close()
