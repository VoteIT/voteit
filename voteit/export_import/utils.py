from __future__ import annotations
import hmac as _hmac
import secrets
from typing import TYPE_CHECKING

import yaml
from django.conf import settings
from django.db import transaction

from voteit.export_import.exceptions import SignatureVerificationFailed


if TYPE_CHECKING:
    from voteit.meeting.models import Meeting

MAX_IMPORT_BYTES = 2 * 1024 * 1024  # 2 MB — signed files
MAX_UNSIGNED_IMPORT_BYTES = 300 * 1024  # 300 KB — unsigned / unverified files


class _NoAliasLoader(yaml.SafeLoader):
    """SafeLoader that rejects YAML anchors/aliases to prevent alias-expansion attacks."""

    def compose_node(self, parent, index):
        if self.check_event(yaml.events.AliasEvent):
            event = self.get_event()
            raise yaml.scanner.ScannerError(
                None, None, "YAML aliases are not permitted", event.start_mark
            )
        return super().compose_node(parent, index)


def get_export_secret(raise_exception=True) -> str | None:
    if secret := getattr(settings, "EXPORT_SECRET_KEY", None):
        if len(secret) > 10:
            return secret
    if raise_exception:
        raise ValueError("No EXPORT_SECRET_KEY or key very short")


def sign_payload(payload: str | bytes) -> str:
    """
    >>> from django.test import override_settings
    >>> from django.test import override_settings
    >>> with override_settings(EXPORT_SECRET_KEY="abcdefghijk"):
    ...     sign_payload("Hello little monkeys")
    'e982e685113ef88acf72f5e28127f1ae296c874f861f0d5d8d522c0d65afe584'

    >>> with override_settings(EXPORT_SECRET_KEY="abcdefghijk"):
    ...     sign_payload(b"Hello little monkeys")
    'e982e685113ef88acf72f5e28127f1ae296c874f861f0d5d8d522c0d65afe584'
    """
    if isinstance(payload, str):
        payload = payload.encode()
    return _hmac.new(get_export_secret().encode(), payload, "sha256").hexdigest()


def verify_signature(payload: str, sign: str):
    """
    >>> from django.test import override_settings
    >>> with override_settings(EXPORT_SECRET_KEY="abcdefghijk"):
    ...     verify_signature("Hello little monkeys", "e982e685113ef88acf72f5e28127f1ae296c874f861f0d5d8d522c0d65afe584")
    True

    ...     verify_signature("Hello little monkeys!", "e982e685113ef88acf72f5e28127f1ae296c874f861f0d5d8d522c0d65afe584")
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
    'c3f9fb1ed798735911f04bb3db6df72fff04550aa03395222ff6ccde3fd8cf15'
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
    'e982e685113ef88acf72f5e28127f1ae296c874f861f0d5d8d522c0d65afe584'

    >>> stream = StringIO('sign: blabla')
    >>> _ = stream.write('Hello little monkeys')
    >>> _ = stream.seek(0)
    >>> with override_settings(EXPORT_SECRET_KEY="abcdefghijk"):
    ...     stream_signature(stream)
    'e982e685113ef88acf72f5e28127f1ae296c874f861f0d5d8d522c0d65afe584'
    """
    first = stream.readline()
    if "sign:" not in first:
        stream.seek(0)
    return sign_payload(stream.read())


def prepare_clone_importer(*, source: Meeting, target: Meeting, **kwargs):
    """
    Export ``source`` and prep an ``Importer`` for ``target`` without running it.

    Used both by ``direct_clone`` and by clone preview, since previewing only
    needs the parsed/validated data - not an actual (rolled back) DB write.
    """
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
    return importer


def direct_clone(*, source: Meeting, target: Meeting, dry_run=True, **kwargs):
    importer = prepare_clone_importer(source=source, target=target, **kwargs)
    with transaction.atomic(durable=True):
        importer()
        if dry_run:
            transaction.set_rollback(True)

    return importer
