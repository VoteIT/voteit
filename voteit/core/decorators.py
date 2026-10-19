from __future__ import annotations

from collections.abc import Callable
from collections.abc import Collection
from functools import wraps
from logging import getLogger
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from django.apps import apps
from django.db import IntegrityError
from django.db.transaction import get_connection
from django.db.transaction import on_commit
from django.middleware.csrf import CsrfViewMiddleware
from django.views.decorators.csrf import csrf_exempt

from voteit.core import RQ_LONG_QUEUE

if TYPE_CHECKING:
    from django.db.models import Manager
    from django.http import HttpRequest
    from django.http import HttpResponseBase
    from voteit.core.role import Role
    from voteit.core.predicate import Predicate

logger = getLogger(__name__)


def predicate(*args, role: Role | None = None, **kwargs) -> Predicate:
    """Decorate predicates with this instead of using rules.predicate

    The method will also add the function to the predicates-registry and wrap
    it in the Predicate class with extended functionality.

    Has the same options as rules.predicate, but accepts role as kw too.

    """
    from voteit.core.registries import predicates

    return predicates(*args, role=role, **kwargs)


def receiver_all_subclasses(signal, sender=None, **kwargs):
    """
    Similar to djangos receiver decorator, but fetches models that subclassed sender
    """
    assert isinstance(sender, type), "This decorator requires sender to be specified"
    if not isinstance(signal, (list, tuple)):
        signal = (signal,)

    def _decorator(func):
        for model in apps.get_models():
            if issubclass(model, sender):
                for s in signal:
                    s.connect(func, sender=model, **kwargs)

        return func

    return _decorator


def ensure_atomic(method):
    """
    Decorator to ensure that something is within an atomic transaction.

    Remember that djangos tests use atomic transactions all the time, but doctests don't.

    >>> @ensure_atomic
    ... def hello():
    ...     pass
    ...

    >>> failed = False
    >>> try:
    ...     hello()
    ... except RuntimeError:
    ...     failed = True
    >>> failed
    True

    >>> from django.db.transaction import atomic
    >>> with atomic():
    ...     hello()
    ...
    """

    def _inner(*args, **kwargs):
        connection = get_connection()
        if not connection.in_atomic_block:
            raise RuntimeError("Must be run while atomic is enabled")
        return method(*args, **kwargs)

    return _inner


def on_transaction_commit(method):
    """
    Delay execution of a function until the database has commited.

    Remember that djangos tests use atomic transactions all the time, but doctests don't.

    Pass by referrence obj
    >>> state = {'done': False}
    >>> @on_transaction_commit
    ... def do_stuff(state):
    ...     state['done'] = True
    ...

    No transaction - will exec right away
    >>> state = {'done': False}
    >>> do_stuff(state)
    >>> state['done']
    True

    Make sure the function runs after an atomic block.
    >>> from django.db.transaction import atomic
    >>> inner_done=False
    >>> state['done'] = False
    >>> with atomic():
    ...     do_stuff(state)
    ...     inner_done=state['done']
    >>> state['done']
    True
    >>> inner_done
    False

    Exceptions should still be raised
    >>> @on_transaction_commit
    ... def loud_bang():
    ...     raise ValueError(':(')
    >>> with atomic():
    ...     loud_bang()
    Traceback (most recent call last):
    ...
    ValueError: ...
    """

    def _inner(*args, **kwargs):
        on_commit(lambda: method(*args, **kwargs))

    return _inner


def disable_on_raw_save(signal_handler):
    """
    Decorator that turns off signal handlers when using raw save. For instance during loaddata and fixtures.
    """

    @wraps(signal_handler)
    def wrapper(*args, **kwargs):
        if kwargs.get("raw"):
            return
        signal_handler(*args, **kwargs)

    return wrapper


def has_exact_filter(*names: str):
    """
    Check that a models.Manager has a specific exact filter applied
    """
    for name in names:
        assert isinstance(name, str)

    def wrapper(f):
        @wraps(f)
        def wrapped(inst: Manager, *args, **kwargs):
            required = set(names)
            qs = inst.get_queryset()
            filters = qs.query.has_filters()
            for ch in filters.children:
                if ch.lookup_name != "exact":
                    continue
                if ch.lhs.field.name in required:
                    required.discard(ch.lhs.field.name)
                    if not required:
                        return f(inst, *args, **kwargs)
            raise IntegrityError(f"Queryset doesn't contain {name} filter")

        return wrapped

    return wrapper


# Filled at import time by @schedule_job, read by voteit.core.cron.
scheduled_jobs: list[dict] = []


def schedule_job(
    cron_string: str,
    *,
    queue_name: str = RQ_LONG_QUEUE,
    result_ttl=3600 * 24 * 7,
    ttl=600,
    timeout=600,
):
    """
    Run the function on a cron schedule. Nothing touches redis here: the
    `rqcron` process picks the job up via voteit.core.cron. Cron strings are
    evaluated in UTC.

    Refresher on cron strings:
    minute (0-59)	hour (0 - 23)	day of the month (1 - 31)	month (1 - 12)	day of the week (0 - 6)

    >>> @schedule_job("1 1 * * 1-5")
    ... def foo():
    ...     pass
    >>> entry = scheduled_jobs.pop()
    >>> entry["func"] is foo, entry["cron"], entry["queue_name"]
    (True, '1 1 * * 1-5', 'long')
    """

    def wrapper(f):
        scheduled_jobs.append(
            {
                "func": f,
                "cron": cron_string,
                "queue_name": queue_name,
                "result_ttl": result_ttl,
                "ttl": ttl,
                "job_timeout": timeout,
            }
        )
        return f

    return wrapper


def url_origin(url: str) -> str:
    """
    The origin of a URL, in the form browsers send in the Origin header.

    >>> url_origin("https://id.example.com/realms/x/")
    'https://id.example.com'
    >>> url_origin("http://localhost:8001")
    'http://localhost:8001'
    """
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def request_origin(request: HttpRequest) -> str | None:
    """
    The request's Origin header, falling back to the origin of the Referer
    header. None when the request carries neither.
    """
    if origin := request.headers.get("Origin"):
        return origin
    if referer := request.headers.get("Referer"):
        return url_origin(referer)


def csrf_exempt_for_origins(
    get_origins: Callable[..., Collection[str]],
) -> Callable[[Callable[..., HttpResponseBase]], Callable[..., HttpResponseBase]]:
    """
    Exempt a view from CSRF checks for requests from the origins
    ``get_origins(request, *args, **kwargs)`` returns. Requests from anywhere
    else get Django's usual CSRF checks, run here since the wrapped view is
    marked csrf_exempt for the middleware.
    """

    def decorator(
        view_func: Callable[..., HttpResponseBase],
    ) -> Callable[..., HttpResponseBase]:
        csrf_middleware = CsrfViewMiddleware(lambda request: None)

        @wraps(view_func)
        def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponseBase:
            origin = request_origin(request)
            if origin is None or origin not in get_origins(request, *args, **kwargs):
                rejection = csrf_middleware.process_view(
                    request, view_func, args, kwargs
                )
                if rejection is not None:
                    return rejection
            return view_func(request, *args, **kwargs)

        return csrf_exempt(_wrapped_view)

    return decorator
