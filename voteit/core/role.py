from __future__ import annotations
from abc import ABC, abstractmethod, ABCMeta
from typing import List, Type, Set, Iterator, TYPE_CHECKING

# from django.contrib.auth.models import AbstractUser
# from django.db.models import ManyToManyField
# from django.db.models import Model
#
# from voteit.core.component import Registry
# from voteit.core.models import Roles
# from voteit.core.signals import role_added
# from voteit.core.signals import role_removed
from django.contrib.auth.models import AbstractUser

if TYPE_CHECKING:
    from voteit.core.models import Roles


class Role:
    name: str
    title: str
    description: str
    requires: Set[Role]
    roles_cls: Type[Roles]

    def __init__(self, name, title=None, description=""):
        self.name = name
        if title is None:
            title = name.title()
        self.title = title
        self.description = description
        self.requires = set()
        self.roles_cls = None  # Will be set when this is attached to a Roles class

    def add_requirement(self, role: Role):
        assert (
            self.roles_cls is not None
        ), "Assign this role to a Roles context first, for instance MeetingRoles"
        assert isinstance(role, Role)
        assert role.roles_cls == self.roles_cls, "Requirements context (roles_cls) doesn't match"
        self.requires.add(role)

    def __repr__(self):
        return self.name


# class RoleMeta(ABCMeta):
#     def __new__(mcls, name, bases, namespace, **kwargs):
#         """ Apologies for this hack, but it's here to make sure that the "requires" attribute is never inherited,
#             since class attributes will otherwise be completely messed up.
#         """
#         cls = super().__new__(mcls, name, bases, namespace, **kwargs)
#         if cls.__name__ != "Role":
#             cls.requires = set()
#         return cls


# class Role(ABC, metaclass=RoleMeta):
#     m2m_relation: ManyToManyField  # Assigned on instantiation
#     # Setting this role requires these other roles to be set too.
#     # The required role must be for the same model as this.
#     requires: Set
#
#     @property
#     @abstractmethod
#     def model(self) -> Type[Model]:
#         """ Required model for this role. """
#
#     @property
#     @abstractmethod
#     def m2m_field(self) -> str:
#         """ The name of the field handling M2M relations on the model you with to handle.
#         """
#
#     @property
#     @abstractmethod
#     def title(self) -> str:
#         """ Human-readable translation string.
#         """
#
#     @property
#     @abstractmethod
#     def name(self) -> str:
#         """ Registered internal name, lowercased class name by default.
#             Used for lookups in roles registry
#         """
#
#     def __init__(self, instance):
#         if not isinstance(instance, self.model):
#             raise TypeError(f"{instance} is not required model {self.model}")
#         self.instance = instance
#         self.m2m_relation = getattr(instance, self.m2m_field)
#         # FIXME: Check that returned attr is a ManyRelatedManager class
#
#     def add(self, *users: List[AbstractUser]):
#         """ Give a list of users this role, and if it depends on some other role,
#             give the users that role too.
#             Example: Discusser role requires someone to be able to view the meeting,
#             so it will require the role Participant.
#         """
#         self.m2m_relation.add(*users)
#         role_added.send(sender=self.__class__, instance=self, users=users)
#         for role_type in self.requires:
#             role = role_type(self.instance)
#             role.add(*users)
#
#     def remove(self, *users: List[AbstractUser]):
#         """ Remove this role from a list of users.
#             If the role that's removed is required by other roles, remove those as well.
#         """
#         self.m2m_relation.remove(*users)
#         role_removed.send(sender=self.__class__, instance=self, users=users)
#         for role_type in roles.get_reverse_required(self.instance, self.__class__):
#             role = role_type(self.instance)
#             role.remove(*users)
#
#     def __contains__(self, user: AbstractUser):
#         return self.m2m_relation.filter(pk=user.pk).exists()
#
#     @classmethod
#     def valid_for(cls, instance):
#         return isinstance(instance, cls.model)
#
#     @classmethod
#     def add_requirement(cls, role: Type[Role]):
#         """ Requirement causes the required role to be added or removed automatically.
#             The two roles must both be for the same model.
#
#             Example:
#                 Discusser requires that someone is a participant of a meeting too.
#
#                 class Participant(Role):
#                     ...
#
#                 class Discusser(Role):
#                     ...
#
#                 Discusser.add_requirement(Participant)
#
#                 When ever someone gets the discusser role, the participant role will be added too.
#                 If the participant role is removed, the discusser role will be removed also.
#         """
#         if role.model != cls.model:
#             raise TypeError(
#                 f"{cls} and {role} doesn't have the same model requirement. "
#             )
#         if cls is role:
#             raise ValueError(f"{cls} can't depend on itself.")
#         cls.requires.add(role)


# class Role(ABC, metaclass=RoleMeta):
#     # Setting this role requires these other roles to be set too.
#     # The required role must be for the same model as this.
#     requires: Set
#
#     # @property
#     # @abstractmethod
#     # def model(self) -> Type[Model]:
#     #     """ Required model for this role. """
#
#     @property
#     @abstractmethod
#     def title(self) -> str:
#         """ Human-readable translation string.
#         """
#
#     @property
#     @abstractmethod
#     def name(self) -> str:
#         """ Registered internal name, lowercased class name by default.
#             Used for lookups in roles registry
#         """

# def add(self, *users: List[AbstractUser]):
#     """ Give a list of users this role, and if it depends on some other role,
#         give the users that role too.
#         Example: Discusser role requires someone to be able to view the meeting,
#         so it will require the role Participant.
#     """
#     self.m2m_relation.add(*users)
#     role_added.send(sender=self.__class__, instance=self, users=users)
#     for role_type in self.requires:
#         role = role_type(self.instance)
#         role.add(*users)
#
# def remove(self, *users: List[AbstractUser]):
#     """ Remove this role from a list of users.
#         If the role that's removed is required by other roles, remove those as well.
#     """
#     self.m2m_relation.remove(*users)
#     role_removed.send(sender=self.__class__, instance=self, users=users)
#     for role_type in roles.get_reverse_required(self.instance, self.__class__):
#         role = role_type(self.instance)
#         role.remove(*users)
#
# def __contains__(self, user: AbstractUser):
#     return self.m2m_relation.filter(pk=user.pk).exists()
#
# @classmethod
# def valid_for(cls, instance):
#     return isinstance(instance, cls.model)

# @classmethod
# def add_requirement(cls, role: Type[Role]):
#     """ Requirement causes the required role to be added or removed automatically.
#         The two roles must both be for the same model.
#
#         Example:
#             Discusser requires that someone is a participant of a meeting too.
#
#             class Participant(Role):
#                 ...
#
#             class Discusser(Role):
#                 ...
#
#             Discusser.add_requirement(Participant)
#
#             When ever someone gets the discusser role, the participant role will be added too.
#             If the participant role is removed, the discusser role will be removed also.
#     """
#     # if role.model != cls.model:
#     #     raise TypeError(
#     #         f"{cls} and {role} doesn't have the same model requirement. "
#     #     )
#     if cls is role:
#         raise ValueError(f"{cls} can't depend on itself.")
#     cls.requires.add(role)


# class AbstractRoleRegistry(Registry, ABC):
#     """ Custom version of the registry.
#     """
#
#     @property
#     @abstractmethod
#     def model(self) -> Model:
#         """ The model this registry is for. Meeting, for instance. """


# def get_valid_roles(self, instance: Model) -> Iterator[Type[Role]]:
#     """ Return all role classes that might be assigned to this instance.
#     """
#     for role in self.values():
#         if role.valid_for(instance):
#             yield role
#
# def get_assigned_roles(self, instance: Model, user: AbstractUser) -> Set:
#     """ Return all classes this user has in this instance.
#     """
#     results = set()
#     for role in self.get_valid_roles(instance):
#         if user in role(instance):
#             results.add(role)
#     return results

# def get_reverse_required(
#     self, instance: Model, role: Type[Role]
# ) -> Iterator[Type[Role]]:
#     """ Figure out which other roles depend on this one.
#     """
#     for other in self.get_valid_roles(instance):
#         if other is role:
#             continue
#         if role in other.requires:
#             yield other


# roles = RoleRegistry(Role)
