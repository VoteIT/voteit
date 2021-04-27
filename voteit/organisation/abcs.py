from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import Dict
from typing import List
from typing import Optional
from typing import TYPE_CHECKING
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.utils.functional import cached_property
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
            username=str(uuid4()),
            identity_id=self.identity_id,
            organisation=organisation,
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

    def get_users(self, default=None) -> Optional[List[AbstractUser]]:
        users = self.User.objects.filter(identity_id=self.identity_id).all()
        users = list(users)
        return users and users or default
