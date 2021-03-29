from logging import getLogger

from django.conf import settings
from django.contrib.auth import login
from django.db import transaction
from django.http import Http404
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from pydantic import ValidationError
from requests_oauthlib import OAuth2Session
from voteit.core.models import OAuth2Provider
from voteit.core.schemas import OAuthStateSchema

logger = getLogger(__name__)


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
        return HttpResponseBadRequest("Login error")
    assert code
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
            user = adapted.register()
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
