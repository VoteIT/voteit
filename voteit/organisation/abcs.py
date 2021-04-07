from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import Optional
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.utils.functional import cached_property
from typing import Dict

from voteit.organisation.schemas import OAuthTokenSchema

if TYPE_CHECKING:
    from voteit.organisation.models import Organisation
    from django.contrib.auth.models import AbstractUser
    from django.contrib.sessions.base_session import AbstractBaseSession


class ProviderResponseAdapter(ABC):
    @cached_property
    def User(self) -> AbstractUser:
        return get_user_model()

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the adapter"""

    def __init__(self, response: Dict):
        self.response = response

    @property
    @abstractmethod
    def identity_id(self) -> str:
        pass

    def register(self, organisation: Organisation):
        return self.User.objects.create(
            username=self.identity_id, organisation=organisation
        )

    @abstractmethod
    def update(self, user: AbstractUser):
        pass

    def store_token(self, session: AbstractBaseSession, token_response: Dict, **kw):
        """
        OAuth information will be used later to make API calls to the identity server.
        """
        # FIXME: We'll want to change this procedure later on
        schema = OAuthTokenSchema(**token_response)
        session["oauth_token"] = schema.dict()
        session.save()

    def get_user(self, default=None):
        user = self.User.objects.filter(username=self.identity_id).first()
        return user and user or default
