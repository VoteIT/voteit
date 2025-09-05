from __future__ import annotations
import hashlib
import secrets
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction

from voteit.export_import.exceptions import SignatureVerificationFailed


if TYPE_CHECKING:
    from voteit.meeting.models import Meeting


def get_export_secret(raise_exception=True) -> str | None:
    if secret := getattr(settings, "EXPORT_SECRET_KEY", None):
        if len(secret) > 10:
            return secret
    if raise_exception:
        raise ValueError("No EXPORT_SECRET_KEY or key very short")


def sign_payload(payload: str | bytes) -> str:
    """
    >>> from django.test import override_settings
    >>> with override_settings(EXPORT_SECRET_KEY="abcdefghijk"):
    ...     sign_payload("Hello little monkeys")
    '1f2b6d9b8c1574d15ad485c07ffeb968278afdb19a90db6dc8dfc3c7a74e9604'

    >>> with override_settings(EXPORT_SECRET_KEY="abcdefghijk"):
    ...     sign_payload(b"Hello little monkeys")
    '1f2b6d9b8c1574d15ad485c07ffeb968278afdb19a90db6dc8dfc3c7a74e9604'
    """
    if isinstance(payload, str):
        payload = payload.encode()
    inst = hashlib.sha256(payload)
    inst.update(get_export_secret().encode())
    return inst.hexdigest()


def verify_signature(payload: str, sign: str):
    """
    >>> from django.test import override_settings
    >>> with override_settings(EXPORT_SECRET_KEY="abcdefghijk"):
    ...     verify_signature("Hello little monkeys", "1f2b6d9b8c1574d15ad485c07ffeb968278afdb19a90db6dc8dfc3c7a74e9604")
    True

    ...     verify_signature("Hello little monkeys!", "1f2b6d9b8c1574d15ad485c07ffeb968278afdb19a90db6dc8dfc3c7a74e9604")
    False

    ...     verify_signature("Hello little monkeys!", None)
    False
    """
    our_sign = sign_payload(payload)
    if sign:
        return secrets.compare_digest(our_sign, sign)
    return False


def _get_sign_from_row(row: str) -> str | None:
    if isinstance(row, bytes):
        row = row.decode()
    items = row.split(":")
    if len(items) == 2 and items[0] == "sign":
        return items[1].strip()


def verify_file(fn):
    """
    >>> from django.test import override_settings
    >>> from voteit.export_import.tests import FIXTURES_DIR
    >>> with override_settings(EXPORT_SECRET_KEY="abcdefghijk"):
    ...     verify_file(f"{FIXTURES_DIR}/ais_and_groups.yaml")
    """
    with open(fn, "r") as stream:
        verify_stream(stream)


def verify_stream(stream):
    sign = _get_sign_from_row(stream.readline())
    if sign is None:
        raise SignatureVerificationFailed("No signature header")
    if not verify_signature(stream.read(), sign):
        raise SignatureVerificationFailed(f"Signature {sign} doesn't match")


def file_signature(fn):
    """
    >>> from django.test import override_settings
    >>> from voteit.export_import.tests import FIXTURES_DIR
    >>> with override_settings(EXPORT_SECRET_KEY="abcdefghijk"):
    ...     file_signature(f"{FIXTURES_DIR}/ais_and_groups.yaml")
    '85b93b98e25c18e6f4ec9b7088701a968f435b53e1353acd5932b1e6846e3f7a'
    """
    with open(fn, "r") as stream:
        return stream_signature(stream)


def stream_signature(stream):
    """
    >>> from django.test import override_settings
    >>> from io import StringIO
    >>> stream = StringIO('Hello little monkeys')
    >>> _ = stream.seek(0)
    >>> with override_settings(EXPORT_SECRET_KEY="abcdefghijk"):
    ...     stream_signature(stream)
    '1f2b6d9b8c1574d15ad485c07ffeb968278afdb19a90db6dc8dfc3c7a74e9604'

    >>> stream = StringIO('sign: blabla')
    >>> _ = stream.write('Hello little monkeys')
    >>> _ = stream.seek(0)
    >>> with override_settings(EXPORT_SECRET_KEY="abcdefghijk"):
    ...     stream_signature(stream)
    '1f2b6d9b8c1574d15ad485c07ffeb968278afdb19a90db6dc8dfc3c7a74e9604'
    """
    first = stream.readline()
    if "sign:" not in first:
        stream.seek(0)
    return sign_payload(stream.read())


def direct_clone(*, source: Meeting, target: Meeting, commit=False, **kwargs):
    from voteit.export_import.exporter import Exporter
    from voteit.export_import.importer import Importer

    import_only_kwargs = {
        x: kwargs.pop(x)
        for x in ["use_existing_groups", "add_participants"]
        if x in kwargs
    }
    exporter = Exporter(source, **kwargs)
    exporter()
    data = exporter.data.dict(exclude_none=True)
    importer = Importer(
        target,
        **kwargs,
        **import_only_kwargs,
    )
    importer.prep_data(data)

    with transaction.atomic(durable=True):
        importer()
        if not commit:
            transaction.set_rollback(True)

    return importer
