""" REST-specific utils"""
from __future__ import annotations

from typing import Dict
from typing import Optional
from typing import TYPE_CHECKING

from rest_framework.exceptions import ValidationError

if TYPE_CHECKING:
    from voteit.core.models import User
    from voteit.organisation.models import OAuth2Provider


def get_identity_data(user: User) -> Dict:
    """
    Returns users identity data from identity server
    """
    try:
        provider: Optional[OAuth2Provider] = user.organisation.provider
    except AttributeError:
        raise ValidationError(
            "Your user isn't attached to an organisation so login this way will never work"
        )
    if provider is None:
        raise ValidationError("No login provider found for your organisation")
    oauth_session = user.oauth_session()
    response = oauth_session.get(provider.identity_url)
    if not response.ok:
        # Not the correct serializer exception, but this is kind of the crash and burn...
        # FIXME: Cases to handle: Token expired, user not found etc
        response.raise_for_status()
    return response.json()
