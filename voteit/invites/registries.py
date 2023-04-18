from contextlib import suppress
from typing import TypeVar

from pydantic import validator
from pydantic.main import BaseModel

from voteit.core.component import Registry
from voteit.invites.abcs import InviteDataAdapter
from voteit.invites.abcs import InviteUserDataAdapter

T = TypeVar("T")


class InviteAdapterRegistry(Registry):

    # def get_user_data_schema(self) -> type[BaseModel]:
    #     from voteit.invites.schemas import CombinedInviteSchema as Base
    #
    #     class UserDataSchema(Base, *[x.schema for x in self.values() if x.user_data]):
    #         ...
    #
    #     return UserDataSchema
    #
    # def get_annotations_schema(self) -> type[BaseModel]:
    #     class AnnotationsSchema(*[x.schema for x in self.values() if not x.user_data]):
    #         class Config:
    #             frozen = True
    #
    #     return AnnotationsSchema
    #
    # def get_combined_schema(self) -> type[BaseModel]:
    #     """
    #     >>> Schema = invite_adapter_registry.get_combined_schema()
    #     >>> breakpoint()
    #     >>> data = Schema(items={('email', 'jeff@betahaus.net'): [('group', 'abc')]})
    #     >>> data.dict(exclude_unset=True)
    #     """
    #     annotations = self.get_annotations_schema()
    #     ud = self.get_user_data_schema()
    #
    #     class CombinedSchema(BaseModel):
    #         items: dict[tuple[str, str], list[tuple[str, str]]]
    #
    #         @validator("items", pre=True)
    #         def validate_ud_tuple_keys(cls, v: dict[tuple[str, str]]):
    #             for k in v.keys():
    #                 if len(k) != 2:
    #                     raise ValueError("Tuple must have 2 items")
    #                 if k[0] not in self.user_data_keys:
    #                     raise ValueError(f"{k[0]} is not a valid user_data key")
    #             return v
    #
    #         @validator("items")
    #         def validate_ud_tuple_values(cls, v: dict):
    #             bad_row = []
    #             i = 1
    #             for keys in v.keys():
    #                 ud(keys)
    #
    #             return v
    #
    #     return CombinedSchema

    def __setitem__(self, key: str, factory: type[InviteDataAdapter]):
        """
        >>> testing_reg = InviteAdapterRegistry(InviteDataAdapter)

        >>> class HelloSchema(BaseModel):
        ...     world:int|None
        ...
        >>> @testing_reg
        ... class Hello(InviteUserDataAdapter):
        ...     schema=HelloSchema
        ...     name='hello'

        >>> testing_reg['oh_no'] = Hello
        Traceback (most recent call last):
        ...
        ValueError: If you register <class 'voteit.invites.registries.Hello'> it will clash \
        with existing <class 'voteit.invites.registries.Hello'>. Schema attributes {'world'} are the same
        """
        if issubclass(factory, InviteUserDataAdapter):
            candidate_keys = set(factory.schema.schema()["properties"].keys())
            for v in self.values():
                if not issubclass(v, InviteUserDataAdapter):
                    continue
                clash = candidate_keys.intersection(
                    v.schema.schema()["properties"].keys()
                )
                if clash:
                    raise ValueError(
                        f"If you register {factory} it will clash with existing {v}, schema attributes {clash} are the same"
                    )
            if hasattr(self, "_user_data_keys"):
                delattr(self, "_user_data_keys")
        # if hasattr(self, "_column_names"):
        #     delattr(self, "_column_names")
        super().__setitem__(key, factory)

    def __delattr__(self, key: str):
        if hasattr(self, "_user_data_keys"):
            delattr(self, "_user_data_keys")
        # if hasattr(self, "_column_names"):
        #     delattr(self, "_column_names")
        super().__delattr__(key)

    @property
    def user_data_keys(self) -> set[str]:
        with suppress(AttributeError):
            return self._user_data_keys
        keys = set()
        for v in self.values():
            if issubclass(v, InviteUserDataAdapter):
                keys.update(v.schema_keys())
        self._user_data_keys = keys
        return keys

    # @property
    # def column_names(self) -> set[str]:
    #     with suppress(AttributeError):
    #         return self._column_names
    #     names = set()
    #     for v in self.values():
    #         names.update(v.columns)
    #     self._column_names = names
    #     return names


invite_adapter_registry = InviteAdapterRegistry(InviteDataAdapter)
