from django.contrib.auth.models import AbstractUser
from voteit.core.utils import generate_valid_userid
from voteit.organisation.abcs import ProviderResponseAdapter
from voteit.organisation.registries import provider_response_adapters
from voteit.organisation.roles import ROLE_ORG_MANAGER


@provider_response_adapters
class IDProxy(ProviderResponseAdapter):
    # FIXME: This is a testing demo
    name = "idproxy"

    @property
    def identity_id(self) -> str:
        return self.response["identity_id"]

    def update(self, user: AbstractUser):
        given_name = self.response.get("given_name", None)
        if given_name:
            user.first_name = given_name
        family_name = self.response.get("family_name", None)
        if family_name:
            user.last_name = family_name
        if user.userid is None:
            suggestion = generate_valid_userid(user)
            if suggestion:
                user.userid = suggestion
        identity = self.response.get("identity", None)
        if identity is not None:
            # Handle all scopes here
            # Email - FIXME there might be multiple emails
            for item in identity:
                if item["scope"] == "email":
                    user.email = item["data"]
            # Other identity parts in identity obj?
        # FIXME: This should probably be a setting if we want to trust this or not.
        is_superuser = self.response.get("is_superuser", None)
        if is_superuser and user.organisation is not None:
            user.organisation.add_roles(user, ROLE_ORG_MANAGER)
        user.save()
