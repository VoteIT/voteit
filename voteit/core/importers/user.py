import sys
from pprint import pprint

from django.contrib.auth import get_user_model
from django.db import transaction
from voteit.core.importers.base import BaseImport
from voteit.core.importers.base import BaseImporter
from voteit.core.models import User
from voteit.core.utils import get_model_shortname
from voteit.organisation.models import Organisation

User = get_user_model()


class UserImport(BaseImport):
    name = settings_key = "user"


class UserImporter(BaseImporter):
    import_class = UserImport

    def run(
        self,
        dry=False,
        existing_organisation_pk=None,
    ):
        assert existing_organisation_pk
        organisation = Organisation.objects.get(pk=existing_organisation_pk)
        users = []
        print("Reading users...")
        email_to_import_pk = {}
        username_to_import_pk = {}  # In case of duplicate run!
        import_pk_to_db_pk = {}
        deserialized_organisation = None
        for deserialized in self.load_objects():
            if get_model_shortname(deserialized.object) == "user":
                users.append(deserialized)
                if deserialized.object.email:
                    deserialized.object.email = deserialized.object.email.lower()
                    if deserialized.object.email in email_to_import_pk:
                        raise ValueError(
                            f"Duplicate email address: {deserialized.object.email}"
                        )
                    email_to_import_pk[
                        deserialized.object.email
                    ] = deserialized.object.pk
                if deserialized.object.username in username_to_import_pk:
                    raise ValueError(
                        f"Duplicate username in import: {deserialized.object.username}"
                    )
                username_to_import_pk[
                    deserialized.object.username
                ] = deserialized.object.pk
            if get_model_shortname(deserialized.object) == "organisation":
                if deserialized_organisation is not None:
                    sys.exit("Multiple organisations found in import file")
                deserialized_organisation = deserialized
                # Change organisation pointer
                self.objects_to_handle["organisation"] = {
                    deserialized.object.pk: organisation
                }

        print(f"Handling {len(users)} users")
        existing_qs = User.objects.filter(
            email__in=email_to_import_pk.keys(), organisation=organisation
        )
        for user in existing_qs:
            import_pk_to_db_pk[email_to_import_pk[user.email]] = user.pk
        existing_qs_username = User.objects.filter(
            username__in=username_to_import_pk.keys(), organisation=organisation
        ).exclude(
            pk__in=existing_qs
        )  ## id__in
        for user in existing_qs_username:
            import_pk_to_db_pk[username_to_import_pk[user.username]] = user.pk
        print(
            f"{len(import_pk_to_db_pk)} matching users exist in db. "
            f"{len(users)-len(import_pk_to_db_pk)} new needs to be created..."
        )

        with transaction.atomic():
            for deserialized in users:
                if deserialized.object.pk in import_pk_to_db_pk:
                    # We can just skip these
                    continue
                self.add_obj_to_handle(deserialized)
                self.update_special_fields(deserialized.object)
                self.save_obj(deserialized)
            self.update_deferred()
            # We may have imported all users already
            for old_pk, deserialized in self.objects_to_handle.get("user", {}).items():
                import_pk_to_db_pk[old_pk] = deserialized.object.pk

            # Keep this last!
            if dry:
                print("== Dry-run - aborting transaction ==")
                transaction.set_rollback(True)
        return import_pk_to_db_pk

        #
        # # Walk
        # for deserialized in all_objects:
        #     name = get_model_shortname(deserialized.object)
        #     if name == "meeting":
        #         if name in self.objects_to_handle:
        #             raise ValueError("Multiple meetings found in file")
        #         deserialized_meeting = deserialized
        #     items = self.objects_to_handle.setdefault(name, {})
        #     items[deserialized.object.pk] = deserialized
        # if deserialized_meeting is None:
        #     raise ValueError("No meeting found")
        #
        # import_order = ["meeting", "agenda_item", "speaker_system", "meeting_group"]
        # # FIXME: Figure out ordering from relations that need to be replaced instead.
        #
        # with transaction.atomic():
        #     self.update_special_fields(deserialized_meeting.object)
        #     # FIXME: Set title?
        #     deserialized_meeting.object.title = (
        #         deserialized_meeting.object.title + f"-copy-{now().date()}"
        #     )
        #     self.save_obj(deserialized_meeting)
        #     [
        #         import_order.append(x)
        #         for x in self.objects_to_handle
        #         if x not in import_order
        #     ]
        #     import_order.pop(0)  # Meeting already handled
        #     for name in import_order:
        #         items = self.objects_to_handle[name]
        #         for deserialized in items.values():
        #             self.update_special_fields(deserialized.object)
        #             self.save_obj(deserialized)
        #     self.update_deferred()
        # self.stream.close()
