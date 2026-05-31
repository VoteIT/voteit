from django.core.cache import cache
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _


class LockAlreadyRunning(Exception):
    pass


class LockCooldownActive(Exception):
    pass


class RequestLock:
    """
    Per-session request flood/concurrency guard using Django's cache backend.

    Holds two cache keys per session:
    - processing key: acquired atomically via cache.add while a request runs
    - cooldown key: set briefly after release to throttle rapid re-submission

    Raises LockAlreadyRunning (→ 409) or LockCooldownActive (→ 429) on acquire.
    Always call release() in a finally block.
    """

    def __init__(
        self,
        key: str,
        *,
        processing_ttl: int = 120,
        cooldown_ttl: int = 5,
        already_running_message: str | Promise = _("Operation already in progress."),
        cooldown_message: str | Promise = _(
            "Please wait a few seconds before retrying."
        ),
    ):
        self.key = key
        self.processing_ttl = processing_ttl
        self.cooldown_ttl = cooldown_ttl
        self.already_running_message = already_running_message
        self.cooldown_message = cooldown_message

    def _processing_key(self, session_key: str) -> str:
        return f"{self.key}:processing:{session_key}"

    def _cooldown_key(self, session_key: str) -> str:
        return f"{self.key}:cooldown:{session_key}"

    def acquire(self, request) -> None:
        sk = request.session.session_key
        if not sk:
            request.session.create()
            sk = request.session.session_key
        if cache.get(self._cooldown_key(sk)):
            raise LockCooldownActive(self.cooldown_message)
        if not cache.add(self._processing_key(sk), 1, self.processing_ttl):
            raise LockAlreadyRunning(self.already_running_message)

    def release(self, request) -> None:
        sk = request.session.session_key
        if not sk:
            return
        cache.delete(self._processing_key(sk))
        cache.add(self._cooldown_key(sk), 1, self.cooldown_ttl)
