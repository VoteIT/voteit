from pydantic.main import BaseModel

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


invite_data = InviteDataRegistry(BaseModel)
# invite_dispatchers = Registry(InviteDispatcher)
