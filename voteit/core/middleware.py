from __future__ import annotations


class SentryUserMiddleware:
    """
    Tell Sentry who a request belongs to, and nothing else about them.

    ``send_default_pii`` is off, which is what keeps request bodies, headers,
    cookies and IP addresses out of Sentry -- but it also stops the Django
    integration attaching any user at all. A primary key is enough to find the
    account here when an error needs chasing, and is the only part of a person
    that has any business leaving the server.

    Only added to ``MIDDLEWARE`` when a ``SENTRY_DSN`` is configured.
    """

    def __init__(self, get_response):
        # Imported here rather than at module scope: sentry_sdk lives in the
        # `docker` extra, so it is absent from a plain dev install -- and this
        # module is imported by anything that walks the package, the doctest
        # loader included. Nothing instantiates this unless a SENTRY_DSN put it
        # in MIDDLEWARE, and there the package is present.
        import sentry_sdk

        self.sentry_sdk = sentry_sdk
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            self.sentry_sdk.set_user({"id": user.pk})
        return self.get_response(request)
