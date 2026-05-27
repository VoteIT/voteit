from django.core.management import BaseCommand
from django.test import override_settings

from voteit.export_import.exceptions import SignatureVerificationFailed
from voteit.export_import.utils import file_signature
from voteit.export_import.utils import verify_file


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
    Signature invalid, should be 905e4c9227b6d166ef6365f0b5d8306733367f31ec255077bb22c8c5f675cdb0
    """

    help = "Import file tools"

    def add_arguments(self, parser):
        parser.add_argument("filename", help="Filename")
        parser.add_argument("--secret", help="Override secret")

    def handle(self, *args, **options):
        filename = options["filename"]
        kwargs = {}
        if override_secret := options.get("secret"):
            kwargs["EXPORT_SECRET_KEY"] = override_secret
        with override_settings(**kwargs):
            try:
                verify_file(filename)
                self.stdout.write(self.style.SUCCESS("Signature is valid"))
            except SignatureVerificationFailed:
                self.stdout.write(
                    self.style.ERROR(
                        f"Signature invalid, should be {file_signature(filename)}"
                    )
                )
