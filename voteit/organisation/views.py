from __future__ import annotations

from logging import getLogger
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import login
from django.db import transaction
from django.http import Http404
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from pydantic import ValidationError
from requests_oauthlib import OAuth2Session

from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation
from voteit.organisation.schemas import OAuthStateSchema

logger = getLogger(__name__)


def begin_auth(request, org_pk: int):
    # FIXME: Very early, for testing
    organisation = get_object_or_404(Organisation, pk=org_pk)
    provider = organisation.provider
    if not provider:
        raise Http404("No provider for organisation")
    # Get scopes from organisation or provider?
    # Note: This is not for security, only to make sure a cookie has been set for the same domain
    # the user will be returned to :)
    redirect_host = urlparse(provider.redirect_url).netloc
    if redirect_host != request.META["HTTP_HOST"]:
        return HttpResponseBadRequest(
            "host in redirect_url and request host doesn't match, login would never work. Host must be: %s"
            % redirect_host,
        )
    auth_session = OAuth2Session(
        client_id=provider.client_id,
        scope=provider.scopes,
        redirect_uri=provider.redirect_url,
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


def finish_auth(request):
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
        raise Http404("State data not saved")
    provider: OAuth2Provider = get_object_or_404(
        OAuth2Provider, pk=state_data.provider_pk
    )
    print("BEGIN finish auth")
    auth_session = OAuth2Session(
        client_id=provider.client_id,
        redirect_uri=provider.redirect_url,
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
    print("Access token fetched")
    print(token_response)

    # FIXME: Store access token etc in session storage or in separate storage
    # {'access_token': 'BVeSgx9s2DZrtutOJ4cup2kEXqrChM', 'expires_in': 36000, 'token_type': 'Bearer',
    #  'scope': ['read', 'write', 'introspection'], 'refresh_token': 'caw8mpEeBXabHJAwai8qoGfMLAhmwL',
    #  'expires_at': 1616031627.091756}

    print("Query identity")
    identity_response = auth_session.get(provider.identity_url)
    data = identity_response.json()
    print("Identity response:")
    print(data)
    adapted = provider.response_adapter(data)
    user = adapted.get_user()
    with transaction.atomic():
        if user:
            print(f"Got user {user}")
        else:
            # register
            print(f"Creating new user")
            user = adapted.register(organisation=provider.organisation)
            print(f"Created user {user}")
        adapted.update(user)
        adapted.store_token(token_response)
        print("Logging in")
        # Any session login kind with http only cookie would do
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        print("Login complete")
        # We might want to save token etc
        request.session.pop("oauth_state", None)
        request.session.save()
    # FIXME: Frontend server
    next_url = "localhost:8080" + state_data.next
    return HttpResponse(f"You're logged in, go here next: {next_url}")
