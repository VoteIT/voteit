from django.contrib.auth.models import AbstractUser
from voteit.core.abcs import ProviderResponseAdapter
from voteit.core.registries import provider_response_adapters


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
        identity = self.response.get("identity", None)
        if identity is not None:
            # Handle all scopes here
            # Email
            email = identity.get("email", None)
            if email and email["validated"]:
                user.email = email["email"]
            # Other identity parts in identity obj?
        user.save()
