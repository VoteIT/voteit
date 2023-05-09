from __future__ import annotations

from abc import abstractmethod
from datetime import datetime
from logging import getLogger
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import models
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField
from django_fsm import transition

from voteit.core.abcs import ABCModel
from voteit.core.abcs import OrganisationContext
from voteit.core.fields import RichTextField
from voteit.core.role import Role
from voteit.core.signals import roles_added
from voteit.core.signals import roles_removed
from voteit.core.utils import strict_clean_html
from voteit.core.validators import UserIDValidator
from voteit.core.workflows import UserWf

if TYPE_CHECKING:
    from requests_oauthlib import OAuth2Session
    from voteit.organisation.models import Organisation
    from voteit.organisation.models import AccessToken


__all__ = ("RoleContextMixin", "Roles", "BaseContent", "User")


logger = getLogger(__name__)


class User(AbstractUser):
    """Custom user model linked to organisation"""

    name = "user"
    userid_validator = UserIDValidator()

    state: str = FSMField(
        default=UserWf.initial, choices=UserWf.choices(), editable=False
    )
    # Note that this is only null to make testing easier, it should never be null!
    organisation: Organisation | None = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.CASCADE,
        null=True,
        related_name="users",
    )
    # Some meetings may require this to be set
    userid: str | None = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        validators=[userid_validator],
    )
    identity_id: str | None = models.CharField(max_length=80, blank=True, null=True)
    img_url: str | None = models.URLField(
        "Profile image url", blank=True, null=True
    )  # FIXME Validator and scheme

    importers = {"user": {}, "organisation": {}}

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["userid", "organisation"], name="unique org userid"
            ),
        ]

    def __str__(self):
        if self.userid:
            return f"{self.get_full_name()} ({self.userid}) {self.organisation_id}"
        return f"[{self.username}] {self.organisation_id}"

    def valid_userid_guard(self) -> bool:
        """
        Check if user has a valid userid
        """
        if self.userid:
            try:
                self.userid_validator(self.userid)
                return True
            except ValidationError:
                pass
        return False

    @transition(
        field=state,
        source="+",
        target=UserWf.ACTIVE,
        conditions=[valid_userid_guard],
        custom={"title": _("Make user active")},
        # permission=Organisation manager or not manual?,
    )
    def activate(self):
        pass

    @transition(
        field=state,
        source="+",
        target=UserWf.INCOMPLETE,
        custom={"title": _("Mark user as incomplete")},
        # permission=Organisation manager or not manual?,
    )
    def incomplete(self):
        pass

    def oauth_session(self) -> OAuth2Session:
        access_token: AccessToken | None = self.access_tokens.filter(
            provider=self.organisation.provider
        ).first()
        if access_token is None:
            raise PermissionDenied("No access token. Please login again.")
        return access_token.get_session()

    objects = UserManager()

    # Annotations
    last_read_set: models.QuerySet
    access_tokens: models.QuerySet
    organisation_id: int | None


def real_user_only(method):
    """Role method should never return true for anon users."""

    def _inner(context, user, *args, **kwargs):

        if not user.is_authenticated:
            return set()  # OK as bool false too
        return method(context, user, *args, **kwargs)

    return _inner


class RoleContextMixin(OrganisationContext):
    """A model where roles can be assigned."""

    @property
    @abstractmethod
    def roles_cls(self) -> Roles:
        """
        Return the Roles class that this context uses.
        """

    def add_roles(self, user: User, *roles: Role) -> set[Role] | None:
        assert isinstance(user, User)
        roles_model, created = self.roles_cls.objects.get_or_create(
            user=user, context=self
        )
        return roles_model.add(*roles)

    def remove_roles(self, user: User, *roles: Role) -> set[Role] | None:
        assert isinstance(user, User)
        roles_model = self.roles_cls.objects.filter(user=user, context=self).first()
        if roles_model is not None:
            return roles_model.remove(*roles)

    @real_user_only
    def get_roles(self, user: User) -> set[Role] | None:
        roles_model = self.roles_cls.objects.filter(user=user, context=self).first()
        if roles_model is not None:
            # Note, may raise AssertionError if some roles are invalid
            roles = roles_model.validate_roles(*roles_model.assigned)
            if roles:
                return roles
        return None

    @real_user_only
    def has_roles(self, user: User, *roles: str | Role) -> bool:
        q = self.roles_to_strings(*roles)
        return self.roles_cls.objects.filter(
            user=user, context=self, assigned__contains=q
        ).exists()

    @real_user_only
    def has_any_roles(self, user: User, *roles: str | Role) -> bool:
        q = self.roles_to_strings(*roles)
        return self.roles_cls.objects.filter(
            user=user, context=self, assigned__overlap=q
        ).exists()

    def get_userids_with_roles(self, *roles: str | Role):
        q = self.roles_to_strings(*roles)
        return self.roles_cls.objects.filter(
            context=self,
            assigned__contains=q,
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

    def filter_valid_roles(self, *roles: Role | str) -> set[str]:
        items = self.roles_to_strings(*roles)
        return {x for x in items if x in self.roles_cls.valid_roles}

    class Meta:
        abstract = True


class Roles(ABCModel):
    """Context for role assignments"""

    valid_roles: dict = None  # Don't instantiate dict here!
    # It's a good idea to override the user relation to have a sane related_name
    user: User = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="roles_%(app_label)s_%(class)s",
    )
    assigned: list[str] = ArrayField(models.CharField(max_length=20), default=tuple)

    @property
    @abstractmethod
    def context(self) -> RoleContextMixin:
        """
        Create a ForeignKey relation to the model that acts as context for this roleset. For instance Meeting
        """

    class Meta:
        abstract = True
        # Note: This isn't inherited to any other subclassing model!
        unique_together = (("user", "context"),)

    def add(self, *roles: Role | str) -> set[Role] | None:
        checked = self.validate_roles(*roles)
        assigned = set(self.assigned)
        query_add = {x.name for x in self.get_required_roles(*checked)}
        new_roles = query_add - assigned
        if new_roles:
            self.assigned = sorted(set(self.assigned) | new_roles)
            self.save()
            role_objs = [self.valid_roles[x] for x in new_roles]
            roles_added.send(sender=self.__class__, instance=self, roles=role_objs)
            return role_objs
        return None

    def remove(self, *roles: Role | str) -> set[Role] | None:
        checked = self.validate_roles(*roles)
        assigned = set(self.assigned)
        query_remove = {x.name for x in self.get_reverse_required_roles(*checked)}
        remove_roles = assigned & query_remove
        if remove_roles:
            self.assigned = sorted(set(self.assigned) - remove_roles)
            self.save()
            role_objs = [self.valid_roles[x] for x in remove_roles]
            roles_removed.send(sender=self.__class__, instance=self, roles=role_objs)
            # Cleanup roles if all were removed
            if not self.assigned:
                self.delete()
            return role_objs
        return None

    def get_required_roles(self, *roles: Role) -> set[Role]:
        required = set()
        for x in roles:
            required.add(x)
            if x.requires:
                required.update(self.get_required_roles(*x.requires))
        return required

    def get_reverse_required_roles(self, *roles: Role) -> set[Role]:
        """If you aim to remove for instance the role Proposer - the participant role will be removed also."""
        required = set()
        to_check = set(roles)
        for role in self.valid_roles.values():
            if role.requires & to_check or role in to_check:
                required.add(role)
        return required

    def validate_roles(self, *roles: Role | str) -> set[Role]:
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

    def __contains__(self, role: Role | str):
        if isinstance(role, Role):
            role = role.name
        return role in self.assigned

    @classmethod
    def related_model_natural_key(cls) -> str:
        related = cls.context.field.related_model
        return f"{related._meta.app_label}.{related._meta.model_name.lower()}"

    def save(self, **kwargs):
        if self.user.organisation is None:
            # Just skip this
            ...
        elif self.context.organisation is None:
            logger.warning(
                f"Context {self.context} has no organisation, assigning user roles blindly"
            )
        else:
            if self.user.organisation != self.context.organisation:
                raise IntegrityError(
                    f"User {self.user} is attached to another organisation."
                )
        super().save(**kwargs)

    # annotations
    objects: models.Manager


class BaseContent(ABCModel):
    body: str = RichTextField(blank=True, default="", html_cleaner=strict_clean_html)
    created: datetime = models.DateTimeField(editable=False, default=now)
    author: User | None = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        related_name="author_%(app_label)s_%(class)s",
    )
    modified: datetime = models.DateTimeField(editable=False, auto_now=True)
    last_modified_by: User | None = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        related_name="last_modified_%(app_label)s_%(class)s",
    )
    mentions = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="mentions_%(app_label)s_%(class)s",
        blank=True,
    )
    tags: list[str] = ArrayField(
        models.CharField(max_length=100), default=list, blank=True, editable=True
    )

    class Meta:
        abstract = True

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self}>"

    def __str__(self):
        for attr in ("title", "body"):
            v = getattr(self, attr, None)
            if v:
                break
        if not v:
            v = f"M:{self.pk}"
        return v[:50]
