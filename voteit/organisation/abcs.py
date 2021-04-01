from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import Optional
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.utils.functional import cached_property
from typing import Dict

if TYPE_CHECKING:
    from voteit.organisation.models import Organisation
    from django.contrib.auth.models import AbstractUser


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

    def store_token(self, token_response: Dict, **kw):
        # FIXME: Perhaps implement this later?
        pass

    def get_user(self, default=None):
        user = self.User.objects.filter(username=self.identity_id).first()
        return user and user or default
