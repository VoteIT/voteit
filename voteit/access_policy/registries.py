from pydantic.main import BaseModel
from typing import Dict
from voteit.access_policy.models import AccessPolicy
from voteit.core.component import Registry


class InviteDataRegistry(Registry):
    """
    Registry fetches name from schema and checks that schema only has valid searchable types.

    >>> from pydantic import BaseModel
    >>> @invite_data
    ... class MyType(BaseModel):
    ...     stuff: int
    ...

    This causes the above type to be registered as "stuff"
    >>> "stuff" in invite_data
    True

    Invite data models can't have several attributes though, due to a limitation in how
    JSONFields handle search.

    >>> @invite_data
    ... class NewType(BaseModel):
    ...     hello: int
    ...     world: str
    Traceback (most recent call last):
    ...
    AssertionError:

    Duplicate data keys aren't allowed either
    >>> @invite_data
    ... class Other(BaseModel):
    ...     stuff: int
    Traceback (most recent call last):
    ...
    KeyError:

    """

    def __call__(self, factory):
        assert issubclass(factory, BaseModel), "Must be a pydantic BaseModel"
        props = factory.schema()["properties"]
        assert len(props) == 1, "Must have exactly one named field"
        name = tuple(props.keys())[0]
        if name in self:
            raise KeyError("%s clashes with an already registered name" % name)
        self[name] = factory
        return factory

    def validate(self, data: Dict):
        """
        Validate invite data to make sure we don't store things that would never work.

        >>> invite_data.validate({"email": "hello@world.com"})

        >>> invite_data.validate({"bleh": 1})
        Traceback (most recent call last):
        ...
        ValueError:

        >>> invite_data.validate({"email": 1})
        Traceback (most recent call last):
        ...
        ValidationError:

        >>> invite_data.validate({"email": None})
        Traceback (most recent call last):
        ...
        ValidationError:

        """
        no_such_data = set(data.keys()) - set(self.keys())
        if no_such_data:
            raise ValueError(
                "data contains keys that doesn't match registered types: %s",
                no_such_data,
            )
        for (k, v) in data.items():
            # Transform and validate
            self[k](**{k: v})  # Might raise pydantics ValidationError


access_policies = Registry(AccessPolicy)
invite_data = InviteDataRegistry(BaseModel)
