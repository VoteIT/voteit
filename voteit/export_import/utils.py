import hashlib
import secrets

from django.conf import settings


def get_export_secret(raise_exception=True) -> str | None:
    if secret := getattr(settings, "EXPORT_SECRET_KEY", None):
        if len(secret) > 10:
            return secret
    if raise_exception:
        raise ValueError("No EXPORT_SECRET_KEY or key very short")


def sign_payload(text: str) -> str:
    """
    >>> from django.test import override_settings
    >>> with override_settings(EXPORT_SECRET_KEY="abcdefghijk"):
    ...     sign_payload("Hello little monkeys")
    '1f2b6d9b8c1574d15ad485c07ffeb968278afdb19a90db6dc8dfc3c7a74e9604'
    """
    inst = hashlib.sha256(text.encode())
    inst.update(get_export_secret().encode())
    return inst.hexdigest()


def verify_signature(text: str, sign: str):
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
    our_sign = sign_payload(text)
    if sign:
        return secrets.compare_digest(our_sign, sign)
    return False
