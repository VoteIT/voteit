from __future__ import annotations

from django.http import HttpRequest
from social_django import views as social_views

from voteit.core.decorators import csrf_exempt_for_origins
from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation


def provider_login_origins(request: HttpRequest, backend: str) -> set[str]:
    """
    Origins the organisation's provider for ``backend`` may post logins from.
    """
    host = request.get_host().split(":")[0]
    try:
        provider = Organisation.objects.get(host=host).get_provider(backend)
    except (Organisation.DoesNotExist, OAuth2Provider.DoesNotExist):
        return set()
    if backend_cls := provider.backend:
        return backend_cls.get_login_origins(provider)
    return set()


# social_django's begin view is CSRF protected, but providers send people here
# with a cross-origin POST. See OrganisationBackendMixin.get_login_origins
begin = csrf_exempt_for_origins(provider_login_origins)(social_views.auth)
