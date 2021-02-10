from collections import UserDict
from inspect import isclass, isfunction


class Registry(UserDict):
    """A simple dict registry for classes or other kind of factories.
    Will validate abstract classes and subclasses.

    Usage example:

    >>> class AbstractFoo:
    ...    pass

    >>> foo_registry = Registry(AbstractFoo)

    create a new class to register by class name

    >>> @foo_registry
    ... class MyFoo(AbstractFoo):
    ...     pass

    Will be registered as "myfo"

    You can either specify key by passing it to the decorator or using a name attribute.
    The decorator has priority.

    >>> @foo_registry("foo")
    ... class MyFoo(AbstractFoo):
    ...     pass

    >>> @foo_registry
    ... class MyFoo(AbstractFoo):
    ...     name = "foo_fighters"


    """

    def __init__(self, required):
        if not isinstance(required, type):  # pragma: no coverage
            raise TypeError(f"{required} is not a class")
        self.required = required
        super().__init__()

    def __call__(self, factory_or_name):
        if isinstance(factory_or_name, str):

            def _decorator(cls):
                self[factory_or_name] = cls
                return cls

            return _decorator

        # Class, function or instance
        if isclass(factory_or_name):
            name = getattr(factory_or_name, "name", factory_or_name.__name__.lower())
        elif isfunction(factory_or_name):
            raise ValueError(
                "Assign name to a function through the decorator: decorator('<name>')"
            )
        else:
            # Probably an instance, what do we know :)
            assert hasattr(factory_or_name, "__class__")
            name = getattr(
                factory_or_name, "name", factory_or_name.__class__.__name__.lower()
            )

        self[name] = factory_or_name
        return factory_or_name

    def __setitem__(self, key: str, factory):
        if isinstance(factory, type):
            # Class based factory
            if not issubclass(factory, self.required):
                raise TypeError(f"{factory} isn't any of the required: {self.required}")
            abs_methods = getattr(factory, "__abstractmethods__", None)
            if abs_methods:
                missing = "', '".join(abs_methods)
                raise TypeError(
                    f"{factory} doesn't implement the required abstract methods: '{missing}'"
                )
        else:
            # Object based
            if not isinstance(factory, self.required):
                raise TypeError(
                    f"{factory} isn't an instance of the required: {self.required}"
                )
        super().__setitem__(key, factory)
