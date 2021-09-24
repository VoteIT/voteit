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
            username=str(uuid4()),
            identity_id=self.identity_id,
            organisation=organisation,
        )

    @abstractmethod
    def update(self, user: AbstractUser):
        pass

    def get_users(self, default=None) -> Optional[List[AbstractUser]]:
        users = self.User.objects.filter(identity_id=self.identity_id).all()
        users = list(users)
        return users and users or default
