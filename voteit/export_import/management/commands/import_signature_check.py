import yaml
from django.core.management import BaseCommand
from django.test import override_settings

from voteit.export_import.exceptions import ImportFileError
from voteit.export_import.schemas import ImportMeetingStructure
from voteit.export_import.utils import sign_payload
from voteit.export_import.utils import verify_signature


class Command(BaseCommand):
    """
    >>> import os
    >>> from django.core.management import call_command
    >>> from django.test import override_settings
    >>> from voteit.export_import.tests import FIXTURES_DIR
    >>> bad_sign_fn = os.path.join(FIXTURES_DIR, "bad_signature.yaml")
    >>> combined_meeting_fn = os.path.join(FIXTURES_DIR, "combined_meeting_fixture.yaml")
    >>> with override_settings(EXPORT_SECRET_KEY='abcdefghijk'):
    ...     call_command("import_signature_check", combined_meeting_fn)
    Signature is valid

    >>> with override_settings(EXPORT_SECRET_KEY='abcdefghijk'):
    ...     call_command("import_signature_check", bad_sign_fn)
    Signature invalid, should be 88933fa49bc02484116dad65f71b1e3bb858a12431a88b12f1d0c45915d74297
    """

    help = "Import file tools"

    def add_arguments(self, parser):
        parser.add_argument("filename", help="Filename")
        parser.add_argument("--secret", help="Override secret")

    def handle(self, *args, **options):
        filename = options["filename"]
        with open(filename, "r+") as stream:
            data = yaml.safe_load(stream)
            # FIXME:Other formats
            if not isinstance(data, dict):
                raise ImportFileError("Import file malformed, must be key-value data")
            import_data = ImportMeetingStructure(**data)
            payload = import_data.json(exclude={"meta"})
            kwargs = {}
            if override_secret := options.get("secret"):
                kwargs["EXPORT_SECRET_KEY"] = override_secret
            with override_settings(**kwargs):
                valid_signature = verify_signature(payload, import_data.meta.sign)
                if valid_signature:
                    self.stdout.write(self.style.SUCCESS("Signature is valid"))
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Signature invalid, should be {sign_payload(payload)}"
                        )
                    )
