from __future__ import annotations
from abc import ABC, abstractmethod, ABCMeta

from django.contrib.auth.models import User
from django.db.models import Model
from rules import Predicate
from typing import List, Type, Set, Generator
from voteit.core.component import Registry


class RoleMeta(ABCMeta):
    def __new__(mcls, name, bases, namespace, **kwargs):
        """ Apologies for this hack, but it's here to make sure that the "requires" attribute is never inherited,
            since class attributes will otherwise be completely messed up.
        """
        cls = super().__new__(mcls, name, bases, namespace, **kwargs)
        if cls.__name__ != "Role":
            cls.requires = set()
        return cls


class Role(ABC, metaclass=RoleMeta):
    rule: Predicate
    model: Type[Model]
    m2m_field: str
    title: str  # Human-readable translation string
    name: str  # Registered internal name, lowercased class name by default. Used for lookups in roles registry
    m2m_relation: None  # Assigned on instantiation
    # Setting this role requires these other roles to be set too.
    # The required role must be for the same model as this.
    requires: Set = None

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
        """ Give a list of users this role, and if it depends on some other role,
            give the users that role too.
            Example: Discusser role requires someone to be able to view the meeting,
            so it will require the role Participant.
        """
        self.m2m_relation.add(*users)
        for role in self.requires:
            other = role(self.instance)
            other.add(*users)

    def remove(self, *users: List[User]):
        """ Remove this role from a list of users.
            If the role that's removed is required by other roles, remove those as well.
        """
        self.m2m_relation.remove(*users)
        for role in get_reverse_required(self.instance, self.__class__):
            role_inst = role(self.instance)
            role_inst.remove(*users)

    def __contains__(self, user: User):
        return self.m2m_relation.filter(pk=user.pk).exists()

    @classmethod
    def valid_for(cls, instance):
        return isinstance(instance, cls.model)

    def allowed(self, user: User):
        return self.rule(user, self.instance)

    @classmethod
    def add_requirement(cls, role: Type[Role]):
        if role.model != cls.model:
            raise TypeError(f"{cls} and {role} doesn't have the same model requirement.")
        if cls is role:
            raise ValueError(f"{cls} can't depend on itself.")
        cls.requires.add(role)


roles = Registry(Role)


def get_valid_roles(instance: Model) -> Generator[Type[Role]]:
    """ Return all role classes that might be assigned to this instance.
    """
    for role in roles.values():
        if role.valid_for(instance):
            yield role


def get_assigned_roles(instance: Model, user: User) -> Set:
    """ Return all classes this user has in this instance.
    """
    results = set()
    for role in get_valid_roles(instance):
        if user in role(instance):
            results.add(role)
    return results


def get_reverse_required(instance: Model, role: Type[Role]) -> Generator[Type[Role]]:
    """ Figure out which other roles depend on this one.
    """
    for other in get_valid_roles(instance):
        if other is role:
            continue
        if role in other.requires:
            yield other
