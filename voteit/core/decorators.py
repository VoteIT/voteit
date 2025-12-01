from __future__ import annotations

from functools import wraps
from logging import getLogger
from typing import TYPE_CHECKING

import django_rq
from django.apps import apps
from django.db import IntegrityError
from django.db.transaction import get_connection
from django.db.transaction import on_commit
from rest_framework.exceptions import PermissionDenied
from redis.exceptions import ConnectionError

from voteit.core import RQ_LONG_QUEUE
from voteit.core.permissions import Permission

if TYPE_CHECKING:
    from django.db.models import Manager
    from rest_framework.viewsets import GenericAPIView
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


def has_perm_drf(permission):
    """
    has_perm check on currently logged in user for a DRF method.
    View must implement get_object.
    """
    assert isinstance(permission, Permission)

    def wrapper(f):
        @wraps(f)
        def wrapped(view: GenericAPIView, request, *args, **kwargs):
            obj = view.get_object()
            if not request.user.has_perm(permission, obj):
                raise PermissionDenied(f"Missing required permission {permission}")
            return f(view, request, *args, **kwargs)

        return wrapped

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


def schedule_job(
    cron_string: str,  # Cron string,
    *,
    queue_name: str = RQ_LONG_QUEUE,
    result_ttl=3600 * 24 * 7,
    ttl=600,
    timeout=600,
    id: str = None,
    **kwargs,
):
    """
    Refresher on cron strings:
    minute (0-59)	hour (0 - 23)	day of the month (1 - 31)	month (1 - 12)	day of the week (0 - 6)


    >>> from fakeredis import FakeRedis
    >>> from unittest.mock import patch
    >>> fakeredis = FakeRedis()
    >>> with patch("django_rq.connection_utils.get_redis_connection", return_value=fakeredis):
    ...     @schedule_job("1 1 * * 1-5")
    ...     def foo():
    ...         pass
    ...
    >>> scheduler = django_rq.get_scheduler('long', connection=fakeredis)
    >>> scheduler.count()
    1
    >>> 'foo' in scheduler
    True
    """

    def wrapper(f):
        scheduler = django_rq.get_scheduler(queue_name)
        # FIXME: django_rqs wrapper of scheduler doesn't really respect the default values,
        try:
            scheduler.cron(
                cron_string,
                func=f,
                id=id or f.__name__,
                use_local_timezone=True,
                result_ttl=result_ttl,
                ttl=ttl,
                timeout=timeout,
                **kwargs,
            )
        except ConnectionError:
            logger.warning("Connection error from redis when scheduling %s", f)
        return f

    return wrapper
