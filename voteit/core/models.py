from __future__ import annotations

from abc import ABCMeta, abstractmethod
from inspect import isclass

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.translation import gettext as _
from typing import List, Type, Set, Optional, Dict, Union

from voteit.core.role import Role
from voteit.core.signals import roles_added, roles_removed


class _AbstractModelMeta(ABCMeta, type(models.Model)):
    pass


class ABCModel(models.Model, metaclass=_AbstractModelMeta):
    """ Abstract classes based on ABCMeta don't work in django -
        this is a workaround to make them behave correctly.
        Remove this as soon as it's fixed in django.
    """

    class Meta:
        abstract = True


class RoleContextMixin(ABCModel):
    """ A model where roles can be assigned. """

    @property
    @abstractmethod
    def roles_cls(self):
        """ Return the Roles class that this context uses.
        """

    def add_roles(self, user: AbstractUser, *roles: Role) -> Optional[Set[Role]]:
        assert isinstance(user, AbstractUser)
        roles_model, created = self.roles_cls.objects.get_or_create(
            user=user, context=self
        )
        roles_model.add(*roles)

    def remove_roles(self, user: AbstractUser, *roles: Role) -> Optional[Set[Role]]:
        assert isinstance(user, AbstractUser)
        roles_model = self.roles_cls.objects.filter(user=user, context=self).first()
        if roles_model is not None:
            return roles_model.remove(*roles)

    def has_roles(self, user: AbstractUser, *roles: Union[str, Role]) -> bool:
        q = self.roles_to_strings(*roles)
        return self.roles_cls.objects.filter(
            user=user, context=self, assigned__contains=q
        ).exists()

    def has_any_roles(self, user: AbstractUser, *roles: Union[str, Role]) -> bool:
        q = self.roles_to_strings(*roles)
        return self.roles_cls.objects.filter(
            user=user, context=self, assigned__overlap=q
        ).exists()

    def get_userids_with_roles(self, *roles: Union[str, Role]):
        q = self.roles_to_strings(*roles)
        return self.roles_cls.objects.filter(
            context=self, assigned__contains=q
        ).values_list("user", flat=True)

    def get_userids_with_any_roles(self, *roles):
        q = self.roles_to_strings(*roles)
        return self.roles_cls.objects.filter(
            context=self, assigned__overlap=q
        ).values_list("user", flat=True)

    def roles_to_strings(self, *roles):
        r = []
        for role in roles:
            if isinstance(role, Role):
                r.append(role.name)
            elif isinstance(role, str):
                r.append(role)
            else:
                raise ValueError(f"{role} is not a str or Role object")
        return r

    class Meta:
        abstract = True


class Roles(ABCModel):
    """ Context for role assignments"""

    valid_roles: Dict = None  # Don't instantiate set here!
    # It's a good idea to override the user relation to have a sane related_name
    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="roles_%(app_label)s_%(class)s",
    )
    assigned: List = ArrayField(models.CharField(max_length=20), default=tuple)

    @property
    @abstractmethod
    def context(self) -> models.Model:
        """ Create a ForeignKey relation to the model that acts as context for this roleset. For instance Meeting
        """

    class Meta:
        abstract = True
        unique_together = (("user", "context"),)

    def add(self, *roles: Role) -> Optional[Set[Role]]:
        checked = self.validate_roles(*roles)
        assigned = set(self.assigned)
        query_add = set([x.name for x in self.get_required_roles(*checked)])
        new_roles = query_add - assigned
        if new_roles:
            self.assigned += tuple(new_roles)
            self.save()
            role_objs = [self.valid_roles[x] for x in new_roles]
            roles_added.send(sender=self.__class__, instance=self, roles=role_objs)
            return role_objs
        return None

    def remove(self, *roles: Role) -> Optional[Set[Role]]:
        checked = self.validate_roles(*roles)
        assigned = set(self.assigned)
        query_remove = set([x.name for x in self.get_reverse_required_roles(*checked)])
        remove_roles = assigned & query_remove
        if remove_roles:
            self.assigned = tuple(set(self.assigned) - remove_roles)
            self.save()
            role_objs = [self.valid_roles[x] for x in remove_roles]
            roles_removed.send(sender=self.__class__, instance=self, roles=role_objs)
            return role_objs
        return None

    def get_required_roles(self, *roles: Role) -> Set[Role]:
        required = set()
        for x in roles:
            required.add(x)
            if x.requires:
                required.update(self.get_required_roles(*x.requires))
        return required

    def get_reverse_required_roles(self, *roles: Role) -> Set[Role]:
        """ If you aim to remove for instance the role Proposer - the participant role will be removed also. """
        required = set()
        to_check = set(roles)
        for role in self.valid_roles.values():
            if role.requires & to_check or role in to_check:
                required.add(role)
        return required

    def validate_roles(self, *roles: Union[Role, str]) -> Set[Role]:
        found = set()
        for x in roles:
            if isinstance(x, str):
                x = self.valid_roles[x]
            else:
                assert isinstance(x, Role), f"{x} is not an instance of Role"
            assert (
                x.name in self.valid_roles
            ), f"{x} is not a valid role for this context"
            found.add(x)
        return found

    @classmethod
    def add_valid(cls, *roles: Role):
        """ Assign a Role instance as a valid choice here.
        """
        for role in roles:
            assert isinstance(role, Role)
            assert (
                role.roles_cls is None
            ), "Role already assigned as valid choice on another Roles model"
            role.roles_cls = cls
            if cls.valid_roles is None:
                cls.valid_roles = {}
            cls.valid_roles[role.name] = role

    def __contains__(self, role: Union[Role, str]):
        if isinstance(role, Role):
            role = role.name
        return role in self.assigned


class BaseContent(models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    created = models.DateTimeField(editable=False, auto_now_add=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        related_name="author_%(app_label)s_%(class)s",
    )
    modified = models.DateTimeField(editable=False, auto_now=True)
    last_modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        related_name="last_modified_%(app_label)s_%(class)s",
    )

    class Meta:
        abstract = True

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.title[:50]}>"

    def __str__(self):
        return self.title[:50]
