from __future__ import annotations

from functools import update_wrapper
from inspect import isfunction, isclass, getsource
from logging import getLogger, Logger
from typing import Optional

from django.conf import settings
from rules import Predicate as RulesPredicate
from rules.predicates import NO_VALUE

from voteit.core.component import Registry
from voteit.core.role import Role
from voteit.core.schemas import PredicateOutput


class Predicate(RulesPredicate):
    """
    An extension of the rules Predicate that allows roles to be attached +
    has some methods for explaining what it does. Again, this is ment as help for frontend developers
    and as a way to organise predicates.

    Register base predicates with the registry by decorating them.

    >>> from datetime import datetime
    >>> predicates = PredicateRegistry(Predicate)

    >>> @predicates
    ... def is_monday():
    ...     return datetime.now().isoweekday() == 1


    The decoration will cause it to be a Predicate
    >>> isinstance(is_monday, Predicate)
    True

    And still retain the rules functions
    >>> isinstance(is_monday, RulesPredicate)
    True

    Predicates will register themselves with their funcitons name
    >>> "is_monday" in predicates
    True

    This version may also mark a specific perdicate as a check for a role
    >>> from voteit.core.role import Role
    >>> MUSICIAN = Role("musician")
    >>> @predicates(role=MUSICIAN)
    ... def is_musician(user):
    ...     return hasattr(user, 'instrument')

    They're linked both ways
    >>> is_musician.role == MUSICIAN
    True

    >>> MUSICIAN.predicate == is_musician
    True

    Registering another predicate with the same role will cause an error
    >>> @predicates(role=MUSICIAN)
    ... def is_something(user):
    ...     pass
    Traceback (most recent call last):
    ...
    ValueError: musician is already assigned to the predicate is_musician

    Calling output will get the contents of the predicate:
    >>> is_musician.output().dict(skip_defaults=True, exclude_none=True, exclude={"source",})
    {'name': 'is_musician', 'fullname': 'voteit.core.predicate.is_musician', 'num_args': 1, 'role_name': 'musician'}
    """

    role: Optional[Role] = None
    logger: Logger = getLogger(__name__)  # Attached via registry or this as default
    verbose_permission_log: bool = False
    permission_log_fail_only: bool = True

    @property
    def source(self):
        return getsource(self.fn)

    @property
    def description(self) -> Optional[str]:
        if self.__doc__:
            return self.__doc__

    @property
    def fullname(self):
        return _fullname(self)

    @property
    def role_name(self) -> Optional[str]:
        return self.role and self.role.name or None

    def test(self, obj=NO_VALUE, target=NO_VALUE) -> bool:
        check_result: bool = super().test(obj=obj, target=target)
        if self.verbose_permission_log:
            if self.permission_log_fail_only and check_result:
                return check_result
            self.logger.info(
                "predicate:%s==%s for %s -> %s", self.name, check_result, obj, target
            )
        return check_result

    def output(self) -> PredicateOutput:
        return PredicateOutput.from_orm(self)


class PredicateRegistry(Registry):
    """Behaves like a dict that stores predicates.

    You can decorate predicates with an instance of this registry to turn
    them into rules predicates and register them here.

    >>> predicates = PredicateRegistry(Predicate)
    >>> @predicates
    ... def hello_world():
    ...     pass

    >>> "hello_world" in predicates
    True

    >>> isinstance(hello_world, Predicate)
    True
    """

    def __call__(self, fn=None, name=None, logger=None, role=None, **options):
        """Mimics the behaviour of the @rules.predicate decorator, but injects the predicate in the registry."""
        if not name and not callable(fn):
            name = fn
            fn = None

        def inner(fn):
            if isinstance(fn, Predicate):
                self[fn.name] = fn
            else:
                pred = Predicate(fn, name, **options)
                update_wrapper(pred, fn)

                pred.verbose_permission_log = getattr(
                    settings, "VERBOSE_PERMISSION_LOG", False
                )
                pred.permission_log_fail_only = getattr(
                    settings, "PERMISSON_LOG_FAIL_ONLY", True
                )
                if logger is not None:
                    pred.logger = logger
                if role:
                    if role.predicate is not None:
                        raise ValueError(
                            f"{role} is already assigned to the predicate {role.predicate}"
                        )
                    pred.role = role
                    role.predicate = pred
                self[pred.name] = pred
            return pred

        if fn:
            return inner(fn)
        else:
            return inner


def _fullname(obj):
    if isfunction(obj) or isclass(obj):
        return f"{obj.__module__}.{obj.__name__}"
    else:  # Instance
        return f"{obj.__class__.__module__}.{obj.__name__}"
