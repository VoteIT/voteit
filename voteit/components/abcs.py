from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from contextlib import suppress

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils.functional import cached_property
from pydantic import BaseModel
from pydantic import ValidationError
from rules.contrib.models import RulesModelMixin

from voteit.core.abcs import ABCModel
from voteit.core.component import Registry


# if TYPE_CHECKING:


class Component(RulesModelMixin, ABCModel):
    component_name: str = models.CharField(max_length=30)
    settings_data: dict | None = models.JSONField(
        verbose_name="JSON-serialized settings",
        null=True,
        blank=True,
        encoder=DjangoJSONEncoder,
    )

    class Meta:
        abstract = True

    @property
    @abstractmethod
    def state(self):
        """
        Django FSM field
        """

    @abstractmethod
    def get_registry(self) -> Registry[str, ComponentAdapter]:
        """
        Return adapter registry for this component type
        """

    @cached_property
    def adapter(self) -> type[ComponentAdapter]:
        reg = self.get_registry()
        with suppress(KeyError):
            return reg[self.component_name]

    @property
    def adapted(self) -> ComponentAdapter:
        return self.adapter(self)

    @property
    def is_valid(self):
        if self.adapter is None:
            return False
        schema = self.adapter.schema
        if schema is None:
            return True
        if schema is not None:
            data = self.settings_data
            if data is None:
                data = {}
            elif not isinstance(data, dict):
                return False
            with suppress(ValidationError):
                schema(**data)
                return True
        return False

    @property
    def settings(self) -> BaseModel | None:
        if self.is_valid:
            schema = self.adapter.schema
            if schema is not None:
                return schema(**self.settings_data)

    @settings.setter
    def settings(self, value: dict | BaseModel | None):
        if not self.adapter:
            raise ValueError(f"{self.component_name} is not valid")
        schema = self.adapter.schema
        if schema is None:
            if value is None:  # Don't bother
                return
            raise ValueError(f"Component {self.adapter.name} has no schema")
        if isinstance(value, dict):
            data = schema(**value)
        elif isinstance(value, schema):
            data = value
        else:  # pragma: no cover
            raise ValueError(f"{value} is not a schema or a dict")
        self.settings_data = data.dict()

    def valid_component_name(self) -> bool:
        return self.component_name in self.get_registry()

    def valid_settings(self) -> bool:
        return self.is_valid

    # Type annotations - relations
    objects: models.Manager

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.component_name}>"

    def __str__(self):
        return f"Component: {self.component_name}"


class ComponentAdapter(ABC):
    """
    Handles data for components

    schema
        A Pydantic schema for validation. If it's none, this component has no data.

    disable_on_close
        Disable component when meeting closes

    Not implemented yet:
    multiple
        If context can have multiple instances of this component.
    """

    schema: type[BaseModel] | None = None
    disable_on_close: bool = False
    # multiple: bool = False

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique name of component
        """

    @property
    @abstractmethod
    def title(self) -> str:
        """
        Human-readable title
        """

    def __init__(self, component: Component):
        self.component = component
