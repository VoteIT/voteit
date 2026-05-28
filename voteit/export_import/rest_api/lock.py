from django.core.cache import cache

_PROCESSING_TTL = 120  # seconds — max expected import duration
_COOLDOWN_TTL = 5  # seconds — pause between imports


class ImportAlreadyRunning(Exception):
    pass


class ImportCooldownActive(Exception):
    pass


def _processing_key(session_key: str) -> str:
    return f"import:processing:{session_key}"


def _cooldown_key(session_key: str) -> str:
    return f"import:cooldown:{session_key}"


def acquire_import_lock(request):
    """
    Attempt to acquire the import processing lock for this session.
    Raises ImportCooldownActive (→ 429) if in cooldown.
    Raises ImportAlreadyRunning (→ 409) if import is in progress.
    """
    sk = request.session.session_key
    if not sk:
        request.session.create()
        sk = request.session.session_key

    if cache.get(_cooldown_key(sk)):
        raise ImportCooldownActive("Please wait before re-importing.")

    if not cache.add(_processing_key(sk), 1, _PROCESSING_TTL):
        raise ImportAlreadyRunning("Import already in progress for this session.")


def release_import_lock(request):
    """
    Release the processing lock and start the cooldown.
    Always called in a finally block.
    """
    sk = request.session.session_key
    if not sk:
        return
    cache.delete(_processing_key(sk))
    cache.add(_cooldown_key(sk), 1, _COOLDOWN_TTL)
