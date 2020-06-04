from abc import ABC, abstractmethod

from django.contrib.auth.models import User
from django.db.models import Model, ManyToManyField
from rules import Predicate
from typing import List, Type, Optional
from voteit.core.component import Registry


class Role(ABC):
    rule: Predicate
    model: Type[Model]
    m2m_field: str
    title: str  # Human-readable translation string
    name: str  # Registered internal name, lowercased class name by default. Used for lookups in roles registry
    m2m_relation: None  # Assigned on instantiation

    @property
    @abstractmethod
    def rule(self):
        """ The 'rules'-rule this is checked against. """

    @property
    @abstractmethod
    def model(self):
        """ Required model for this role. """

    @property
    @abstractmethod
    def m2m_field(self):
        """ The name of the field handling M2M relations on the model you with to handle.
        """

    @property
    @abstractmethod
    def title(self):
        """ Translation string.
        """

    @property
    @abstractmethod
    def name(self):
        """ Internal id of the role.
        """

    def __init__(self, instance):
        if not isinstance(instance, self.model):
            raise TypeError(f"{instance} is not required model {self.model}")
        self.instance = instance
        self.m2m_relation = getattr(instance, self.m2m_field)
        # FIXME: Check that returned attr is a ManyRelatedManager class

    def add(self, *users: List[User]):
        self.m2m_relation.add(*users)

    def remove(self, *users: List[User]):
        self.m2m_relation.remove(*users)

    def __contains__(self, user: User):
        return self.m2m_relation.filter(pk=user.pk).exists()

    @classmethod
    def valid_for(cls, instance):
        return isinstance(instance, cls.model)

    def allowed(self, user: User):
        return self.rule(user, self.instance)


roles = Registry(Role)


def get_valid_roles(instance: Model):
    """ Return all role classes that might be assigned to this instance.
    """
    for role in roles.values():
        if role.valid_for(instance):
            yield role


def get_assigned_roles(instance: Model, user: User):
    """ Return all classes this user has in this instance.
    """
    results = set()
    for role in get_valid_roles(instance):
        if user in role(instance):
            results.add(role)
    return results
