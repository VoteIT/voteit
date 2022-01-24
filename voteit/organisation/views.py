from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import login
from django.db import DatabaseError
from django.db import transaction
from django.http import Http404, HttpRequest
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from pydantic import ValidationError
from requests_oauthlib import OAuth2Session
from voteit.organisation.models import AccessToken

from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation
from voteit.organisation.schemas import OAuthStateSchema

if TYPE_CHECKING:
    from voteit.organisation.abcs import ProviderResponseAdapter

logger = getLogger(__name__)


def begin_auth(request):
    # FIXME: Very early, for testing
    host = request.get_host()
    hostname = host.split(":")[0]
    try:
        organisation = Organisation.objects.get(host=hostname)
    except Organisation.DoesNotExist:
        raise Http404("No organisation with host %s" % hostname)

    provider = organisation.provider
    if not provider:
        raise Http404("No provider for organisation")
    # Get scopes from organisation or provider?
    # Note: This is not for security, only to make sure a cookie has been set for the same domain
    # the user will be returned to :)
    redirect_url = provider.redirect_url(request)
    redirect_host = urlparse(redirect_url).netloc
    # if redirect_host != request.META["HTTP_HOST"]:
    if redirect_host != host:
        return HttpResponseBadRequest(
            "host in redirect_url and request host doesn't match, login would never work. Host must be: %s"
            % redirect_host,
        )

    scope = provider.scope
    if "identity" not in scope.split():
        scope += " identity"  # Base identity information
    auth_session = OAuth2Session(
        client_id=provider.client_id,
        scope=scope,
        redirect_uri=redirect_url,
    )
    authorization_url, state = auth_session.authorization_url(
        provider.auth_url,
        approval_prompt="auto",
    )
    # Only local path for "next" - add domain later
    state_data = OAuthStateSchema(
        provider_pk=provider.pk, next=request.GET.get("next", "/"), state=state
    )
    request.session["oauth_state"] = state_data.dict()
    request.session.save()
    return HttpResponseRedirect(authorization_url)


def finish_auth(request: HttpRequest):
    # FIXME: Very early, for testing
    error = request.GET.get("error", None)
    if error is not None:
        return HttpResponseBadRequest(error)
    try:
        data = request.session["oauth_state"]
    except KeyError:
        return HttpResponseBadRequest("No login session")
    try:
        state_data = OAuthStateSchema(**data)
    except ValidationError:
        request.session.pop("oauth_state", None)
        request.session.save()
        if settings.DEBUG:
            raise
        raise Http404("No login in progress")
    request_state = request.GET.get("state", object())
    if state_data.state != request_state:
        request.session.pop("oauth_state", None)
        request.session.save()
        logger.debug("Session stored state doesn't match incoming request state")
        # FIXME: Redirect to...?
        raise Http404("Login process error, please try again")
    provider: OAuth2Provider = get_object_or_404(
        OAuth2Provider, pk=state_data.provider_pk
    )
    auth_session = OAuth2Session(
        client_id=provider.client_id,
        redirect_uri=provider.redirect_url(request),
    )
    # Use token response any other way?
    code = request.GET.get("code", "")
    if not code:
        return HttpResponseBadRequest("Login error - no code param")
    token_response = auth_session.fetch_token(
        provider.token_url,
        code=code,
        client_secret=provider.client_secret,
    )
    logger.debug("Access token fetched, fetching identity")
    identity_response = auth_session.get(provider.identity_url)
    if not identity_response.ok:
        # FIXME: We need to change template or do a redirect here
        # This probably causes errors if the user need to login
        return HttpResponse(status=identity_response.status_code)

    data = identity_response.json()
    logger.debug("Identity response: %s", data)
    adapted: ProviderResponseAdapter = provider.response_adapter(data)
    users = adapted.get_users()
    try:
        with transaction.atomic():
            if users:
                if len(users) > 1:
                    # FIXME: How's this choice made?
                    logger.debug("Identity matched users: %s", [x.pk for x in users])
                    user = users[0]
                else:
                    user = users[0]
                    logger.debug("Identity matched user: %s", user.pk)
            else:
                user = adapted.register(organisation=provider.organisation)
                logger.debug("Creating new user: %s", user.pk)
            adapted.update(user)
            AccessToken.objects.from_response(token_response, user, provider)
            request.session.pop("oauth_state", None)
            request.session.save()
    except DatabaseError:
        # Catch all exceptions here?
        logger.exception("User registration/login failed:")
        next_url = "localhost:8080/failed_login"  # FIXME
        return HttpResponse(f"Login failed, retry: {next_url}")
    else:
        # Any session login kind with http only cookie would do
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        if settings.DEBUG:
            # For dev environment only, redirect back to Vue JS
            hostname = request.get_host().split(":")[0]
            return HttpResponseRedirect(
                f"{request.scheme}://{hostname}:8080" + state_data.next
            )
        return HttpResponseRedirect(state_data.next)
