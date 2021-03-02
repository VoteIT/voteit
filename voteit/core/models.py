from __future__ import annotations

from abc import abstractmethod
from datetime import datetime
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import Union

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.db import models
from voteit.core.abcs import ABCModel
from voteit.core.role import Role
from voteit.core.signals import roles_added
from voteit.core.signals import roles_removed
from voteit.core.utils import get_tagged_hashtags
from voteit.core.utils import get_tagged_userids
from voteit.core.utils import strict_clean_html

User = get_user_model()

__all__ = ("RoleContextMixin", "Roles", "BaseContent")


def real_user_only(method):
    """Role method should never return true for anon users."""

    def _inner(context, user, *args, **kwargs):

        if not user.is_authenticated:
            return set()  # OK as bool false too
        return method(context, user, *args, **kwargs)

    return _inner


class RoleContextMixin(ABCModel):
    """ A model where roles can be assigned. """

    @property
    @abstractmethod
    def roles_cls(self) -> Roles:
        """Return the Roles class that this context uses."""

    def add_roles(self, user: User, *roles: Role) -> Optional[Set[Role]]:
        assert isinstance(user, User)
        roles_model, created = self.roles_cls.objects.get_or_create(
            user=user, context=self
        )
        return roles_model.add(*roles)

    def remove_roles(self, user: User, *roles: Role) -> Optional[Set[Role]]:
        assert isinstance(user, User)
        roles_model = self.roles_cls.objects.filter(user=user, context=self).first()
        if roles_model is not None:
            return roles_model.remove(*roles)

    @real_user_only
    def get_roles(self, user: User) -> Optional[Set[Role]]:
        roles_model = self.roles_cls.objects.filter(user=user, context=self).first()
        if roles_model is not None:
            # Note, may raise AssertionError if some roles are invalid
            roles = roles_model.validate_roles(*roles_model.assigned)
            if roles:
                return roles
        return None

    @real_user_only
    def has_roles(self, user: User, *roles: Union[str, Role]) -> bool:
        q = self.roles_to_strings(*roles)
        return self.roles_cls.objects.filter(
            user=user, context=self, assigned__contains=q
        ).exists()

    @real_user_only
    def has_any_roles(self, user: User, *roles: Union[str, Role]) -> bool:
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

    def filter_valid_roles(self, *roles: Union[Role, str]) -> Set[str]:
        items = self.roles_to_strings(*roles)
        return set([x for x in items if x in self.roles_cls.valid_roles])

    class Meta:
        abstract = True


class Roles(ABCModel):
    """ Context for role assignments"""

    valid_roles: Dict = None  # Don't instantiate dict here!
    # It's a good idea to override the user relation to have a sane related_name
    user: User = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="roles_%(app_label)s_%(class)s",
    )
    assigned: List = ArrayField(models.CharField(max_length=20), default=tuple)

    @property
    @abstractmethod
    def context(self) -> models.Model:
        """Create a ForeignKey relation to the model that acts as context for this roleset. For instance Meeting"""

    class Meta:
        abstract = True
        unique_together = (("user", "context"),)

    def add(self, *roles: Union[Role, str]) -> Optional[Set[Role]]:
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

    def remove(self, *roles: Union[Role, str]) -> Optional[Set[Role]]:
        checked = self.validate_roles(*roles)
        assigned = set(self.assigned)
        query_remove = set([x.name for x in self.get_reverse_required_roles(*checked)])
        remove_roles = assigned & query_remove
        if remove_roles:
            self.assigned = tuple(set(self.assigned) - remove_roles)
            self.save()
            role_objs = [self.valid_roles[x] for x in remove_roles]
            roles_removed.send(sender=self.__class__, instance=self, roles=role_objs)
            # Cleanup roles if all were removed
            if not self.assigned:
                self.delete()
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
        """Assign a Role instance as a valid choice here."""
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

    @classmethod
    def related_model_natural_key(cls) -> str:
        related = cls.context.field.related_model
        return f"{related._meta.app_label}.{related._meta.model_name.lower()}"


class BaseContent(ABCModel):
    body: str = models.TextField(blank=True, default="")
    created: datetime = models.DateTimeField(editable=False, auto_now_add=True)
    author: User = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        related_name="author_%(app_label)s_%(class)s",
    )
    modified: datetime = models.DateTimeField(editable=False, auto_now=True)
    last_modified_by: User = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        related_name="last_modified_%(app_label)s_%(class)s",
    )
    mentions = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="mentions_%(app_label)s_%(class)s",
        editable=False,
    )
    tags: List = ArrayField(
        models.CharField(max_length=100), default=list, editable=False
    )

    class Meta:
        abstract = True

    def html_cleaner(self, text):
        # FIXME: Override in a better way
        return strict_clean_html(text)

    def set_tags(self):
        # FIXME: Should be generic
        current_tags = set(self.tags)
        tags = get_tagged_hashtags(self.body)
        if tags != current_tags:
            self.tags = sorted(tags)

    def set_mentions(self):
        # FIXME: Should be generic
        mentions = get_tagged_userids(self.body)
        current_user_pks = set(self.mentions.all().values_list("pk", flat=True))
        if mentions != current_user_pks:
            # Only real users are allowed as mentions
            result = User.objects.filter(pk__in=mentions).values_list("pk", flat=True)
            self.mentions.set(result)

    def save(self, **kw):
        self.body = self.html_cleaner(self.body)
        self.set_tags()
        super().save(**kw)
        self.set_mentions()

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self}>"

    def __str__(self):
        return getattr(self, "title", self.body)[:50]
