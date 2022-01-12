from typing import List
from pydantic.main import BaseModel

from voteit.invites.abcs import InviteDispatcher
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

    def validate(self, data_type, data: List[str]):
        """
        Validate invite data to make sure we don't store things that would never work.
        Transforms data in place too.

        >>> invite_data.validate("email", ["hello@world.com"])
        ['hello@world.com']

        Invites have their data transformed too
        >>> invite_data.validate("email", ["HELLO@world.com"])
        ['hello@world.com']

        >>> invite_data.validate("bleh", [1])
        Traceback (most recent call last):
        ...
        ValueError:

        >>> invite_data.validate("email", [1])
        Traceback (most recent call last):
        ...
        ValidationError:

        >>> invite_data.validate("email", [None])
        Traceback (most recent call last):
        ...
        ValidationError:

        """
        if not data:
            raise ValueError("Invite must contain data")
        if data_type not in self:
            raise ValueError(f"No such data type: {data_type}")
        results = []
        for v in data:
            # Transform and validate
            schema = self[data_type](
                **{data_type: v}
            )  # Might raise pydantics ValidationError
            results.append(getattr(schema, data_type))
        return results


invite_data = InviteDataRegistry(BaseModel)
invite_dispatchers = Registry(InviteDispatcher)
