from typing import TypeVar

from pydantic.main import BaseModel

from voteit.core.component import Registry
from voteit.invites.abcs import InviteDataAdapter

T = TypeVar("T")


class InviteAdapterRegistry(Registry):
    """
    >>> testing_reg = InviteAdapterRegistry(InviteDataAdapter)

    >>> class HelloSchema(BaseModel):
    ...     world:int|None
    ...
    >>> @testing_reg
    ... class Hello(InviteDataAdapter):
    ...     schema=HelloSchema
    ...     name='hello'
    ...

    >>> from voteit.invites.schemas import CombinedInviteSchema
    >>> issubclass(testing_reg.Schema, CombinedInviteSchema)
    True
    >>> testing_reg.Schema(world=1, maybe=False)
    InviteSchema(world=1)

    >>> testing_reg.Schema(maybe=False)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError: 1 validation error for InviteSchema
    __root__
      At least one value required (type=value_error)
    """

    # @cached_property
    @property
    def Schema(self) -> type[BaseModel]:
        from voteit.invites.schemas import CombinedInviteSchema

        class InviteSchema(CombinedInviteSchema, *[x.schema for x in self.values()]):
            ...

        return InviteSchema

    def __setitem__(self, key: str, factory: type[InviteDataAdapter]):
        """
        >>> testing_reg = InviteAdapterRegistry(InviteDataAdapter)

        >>> class HelloSchema(BaseModel):
        ...     world:int|None
        ...
        >>> @testing_reg
        ... class Hello(InviteDataAdapter):
        ...     schema=HelloSchema
        ...     name='hello'

        >>> testing_reg['oh_no'] = Hello
        Traceback (most recent call last):
        ...
        ValueError: If you register <class 'voteit.invites.registries.Hello'> it will clash \
        with existing <class 'voteit.invites.registries.Hello'>. Schema attributes {'world'} are the same
        """

        candidate_keys = set(factory.schema.schema()["properties"].keys())
        for v in self.values():
            clash = candidate_keys.intersection(v.schema.schema()["properties"].keys())
            if clash:
                raise ValueError(
                    f"If you register {factory} it will clash with existing {v}, schema attributes {clash} are the same"
                )
        super().__setitem__(key, factory)


invite_adapter_registry = InviteAdapterRegistry(InviteDataAdapter)
