from __future__ import annotations
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.models import AbstractUser

from voteit.core.utils import generate_valid_userid
from voteit.organisation.abcs import ProviderResponseAdapter
from voteit.organisation.registries import provider_response_adapters
from voteit.organisation.roles import ROLE_ORG_MANAGER

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from voteit.organisation.models import Organisation

_allowed_url_schemes = ["https"]
if settings.DEBUG:
    _allowed_url_schemes.append("http")


@provider_response_adapters
class IDProxy(ProviderResponseAdapter):
    # FIXME: This is a testing demo
    name = "idproxy"

    @property
    def identity_id(self) -> str:
        return self.response["identity_id"]

    def update(self, user: AbstractUser):
        given_name = self.response.get("given_name", None)
        if given_name and not user.first_name:
            user.first_name = given_name
        family_name = self.response.get("family_name", None)
        if family_name and not user.last_name:
            user.last_name = family_name
        if user.userid is None:
            suggestion = generate_valid_userid(user)
            if suggestion:
                user.userid = suggestion
        img_url = self.response.get("img_url")
        if img_url:
            # We'll have to use trusted sources here
            parsed = urlparse(img_url)
            if parsed.scheme in _allowed_url_schemes:
                user.img_url = img_url
        emails = self.get_emails()
        if emails and user.email not in emails:
            # Any correct email is better than a falsy one...
            user.email = emails.pop()
        # Other identity parts in identity obj?
        # FIXME: This should probably be a setting if we want to trust this or not.
        is_superuser = self.response.get("is_superuser", None)
        if is_superuser and user.organisation is not None:
            user.organisation.add_roles(user, ROLE_ORG_MANAGER)
        user.save()

    def get_inheritable_users(self, organisation: Organisation) -> QuerySet:
        """
        Attach any users who have the identity_id present in extra_identity_ids, they should be moved to the
        primary identity_id. This is for users who've registered several times and then
        after they've started to use their accounts, they've merged their identity provider account.
        """
        qs = super().get_inheritable_users(organisation)
        extra_identity_ids = self.response.get("extra_identity_ids")
        if extra_identity_ids:
            qs = qs.union(
                self.User.objects.filter(
                    identity_id__in=extra_identity_ids,
                    is_active=True,
                    organisation=organisation,
                )
            )
        return qs
