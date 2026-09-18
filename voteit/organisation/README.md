# Linking a login to an account that already exists

A member signs in with ScoutID for the first time. VoteIT has an account for them
already, reachable at the same address but filed under a different name.

    >>> from django.test import Client
    >>> from django.test import RequestFactory
    >>> from django.utils.timezone import now
    >>> from social_django.models import Partial
    >>> from social_django.models import DjangoStorage
    >>> from social_django.strategy import DjangoStrategy
    >>> from voteit.app.scouterna.backends import ScoutIDOpenIdConnect
    >>> from voteit.organisation.models import Organisation

    >>> org = Organisation.objects.create(title="Scouts", host="testserver")
    >>> provider = org.providers.create(
    ...     provider_id="scoutid", client_id="voteit", client_secret="s3cret"
    ... )

The account they already have. One surname here, two in Scoutnet.

    >>> existing = org.users.create(
    ...     username="kim",
    ...     first_name="Kim",
    ...     last_name="Scout",
    ...     email="kim@example.com",
    ...     last_login=now(),
    ... )

ScoutID vouches for the address, which is what the matcher goes on.

    >>> backend = ScoutIDOpenIdConnect()
    >>> backend.__dict__["organisation"] = org
    >>> response = {"email": "kim@example.com", "email_verified": True}
    >>> details = {
    ...     "first_name": "Kim",
    ...     "last_name": "Scout Fieldsson",
    ...     "email": "kim@example.com",
    ... }
    >>> backend.get_verified_email(details, response)
    'kim@example.com'

`match_existing_user` runs in the login pipeline. The name does not match, so it
will not take the account on its own -- it pauses and asks.

    >>> from voteit.organisation.pipeline import match_existing_user

    >>> def run(query=None):
    ...     request = RequestFactory().get("/complete/scoutid/", query or {})
    ...     request.session = {}
    ...     return match_existing_user(
    ...         strategy=DjangoStrategy(DjangoStorage, request=request),
    ...         backend=backend,
    ...         details=details,
    ...         response=response,
    ...         pipeline_index=3,
    ...     )

    >>> paused = run()
    >>> paused.status_code, paused["Location"]
    (302, '/link-account?partial_token=...')

Nothing was created. No account, no credential, nothing to merge away later.

    >>> org.users.count()
    1

The pipeline is stored instead, and the token is the way back into it.

    >>> token = Partial.objects.get().token
    >>> token in paused["Location"]
    True

The screen behind that link reads the choices with the token. Nobody is signed in
yet, so the token is what stands in for a session.

    >>> client = Client()
    >>> options = client.get(
    ...     "/api/account-link-options/", {"partial_token": token}
    ... ).json()
    >>> options["provider"], options["resume_url"]
    ('scoutid', '/complete/scoutid/')

Said plainly. Someone deciding whether an account is theirs is worse served by a
half-hidden address than by the address.

    >>> account, = options["accounts"]
    >>> account["pk"] == existing.pk, account["name"], account["email"]
    (True, 'Kim Scout', 'kim@example.com')

They recognise it and answer. In the browser this is a redirect back to
`resume_url` with the token and the choice, which picks the pipeline up where it
stopped.

    >>> resumed = run({"partial_token": token, "link_account": existing.pk})
    >>> resumed["user"] == existing, resumed["matched_existing"]
    (True, True)

`create_user` then short-circuits on that user and `associate_user` attaches the
credential to it, so the login finishes on the account they already had.

    >>> social = existing.social_auth.create(
    ...     provider="scoutid", uid="a-keycloak-sub", extra_data={}
    ... )
    >>> client.force_login(existing)

Had they not recognised it -- a spouse on the same address, or whoever else reads
`info@someorg.org` -- answering `link_account=new` carries on to a fresh account
instead.

# The other things the matcher decides

The same call, on the rest of the cases.

    >>> def signing_in(first_name, last_name, email, verified=True, answer=None):
    ...     query = {"link_account": answer} if answer else {}
    ...     request = RequestFactory().get("/complete/scoutid/", query)
    ...     request.session = {}
    ...     return match_existing_user(
    ...         strategy=DjangoStrategy(DjangoStorage, request=request),
    ...         backend=backend,
    ...         details={
    ...             "first_name": first_name,
    ...             "last_name": last_name,
    ...             "email": email,
    ...         },
    ...         response={"email": email, "email_verified": verified},
    ...         pipeline_index=3,
    ...     )

    >>> def outcome(result):
    ...     if not isinstance(result, dict):
    ...         return "asked"
    ...     return result["user"].username if result.get("user") else "new account"

## Nothing on the address

    >>> outcome(signing_in("Nour", "Scout", "nobody@example.com"))
    'new account'

## An address the provider will not vouch for

    >>> _ = org.users.create(
    ...     username="unverified",
    ...     first_name="Nour",
    ...     last_name="Scout",
    ...     email="nour@example.com",
    ...     last_login=now(),
    ... )
    >>> outcome(signing_in("Nour", "Scout", "nour@example.com", verified=False))
    'new account'

## One account, same name, somebody has used it: taken silently

    >>> outcome(signing_in("Nour", "Scout", "nour@example.com"))
    'unverified'

## Nobody has ever logged into it

Nobody has proved it is theirs -- including whoever is asking.

    >>> never = org.users.create(
    ...     username="never-used",
    ...     first_name="Alex",
    ...     last_name="Scout",
    ...     email="alex@example.com",
    ... )
    >>> outcome(signing_in("Alex", "Scout", "alex@example.com"))
    'asked'

Answering with that account links it; answering `new` does not.

    >>> outcome(signing_in("Alex", "Scout", "alex@example.com", answer=never.pk))
    'never-used'
    >>> outcome(signing_in("Alex", "Scout", "alex@example.com", answer="new"))
    'new account'

An account that was never among the choices is refused, whatever the browser sends.

    >>> outcome(signing_in("Alex", "Scout", "alex@example.com", answer=existing.pk))
    'asked'

## Two accounts with the same name and address

    >>> for username in ("twin-a", "twin-b"):
    ...     _ = org.users.create(
    ...         username=username,
    ...         first_name="Sasha",
    ...         last_name="Scout",
    ...         email="twins@example.com",
    ...         last_login=now(),
    ...     )
    >>> outcome(signing_in("Sasha", "Scout", "twins@example.com"))
    'asked'

## One mailbox, several people

`info@someorg.org`, or a couple sharing an address. The one carrying the name is
still taken silently -- the others are simply somebody else.

    >>> for username, first_name in (("info-a", "Mio"), ("info-b", "Noa")):
    ...     _ = org.users.create(
    ...         username=username,
    ...         first_name=first_name,
    ...         last_name="Scout",
    ...         email="info@someorg.org",
    ...         last_login=now(),
    ...     )
    >>> outcome(signing_in("Mio", "Scout", "info@someorg.org"))
    'info-a'

Arrive under a name neither of them carries, and they are asked which is theirs.

    >>> outcome(signing_in("Ida", "Scout", "info@someorg.org"))
    'asked'

## The account carries org roles

The one case that is refused outright. A second account for a manager is a merge
waiting to happen, so they are sent back to the login they already have.

    >>> from voteit.organisation.roles import ROLE_ORG_MANAGER
    >>> manager = org.users.create(
    ...     username="manager",
    ...     first_name="Kai",
    ...     last_name="Scout",
    ...     email="manager@example.com",
    ...     last_login=now(),
    ... )
    >>> _ = org.add_roles(manager, ROLE_ORG_MANAGER)
    >>> signing_in("Kai", "Scout", "manager@example.com")
    Traceback (most recent call last):
    social_core.exceptions.AuthForbidden: ...

The message reaches the SPA through `GET /api/user/messages/`, by way of
`SocialAuthExceptionMiddleware`. An org manager on the same address under another
name is somebody else, and neither blocks nor is offered.

    >>> outcome(signing_in("Ida", "Scout", "manager@example.com"))
    'new account'

# Taking a login method back off

Every link is undoable, including the last one: a credential can land on the wrong
account, and whoever it belongs to has to be able to take it back.

    >>> connections = client.get("/api/user/connections/").json()
    >>> [(c["provider"], c["is_only_login_method"]) for c in connections]
    [('scoutid', True)]

    >>> client.post("/api/user/disconnect/", {"provider": "scoutid"}).status_code
    204
    >>> client.get("/api/user/connections/").json()
    []

The account is now unreachable, which is where a never-used one started.

# Connecting another login method, on purpose

Going the other way. A signed-in account only picks up a new login method because
somebody asked for it, so the asking is recorded first.

    >>> client.post("/api/user/connect/", {"provider": "scoutid"}).json()
    {'provider': 'scoutid', 'login_url': '/login/scoutid/'}

    >>> from voteit.organisation.pipeline import CONNECT_INTENT_SESSION_KEY
    >>> client.session[CONNECT_INTENT_SESSION_KEY]
    'scoutid'

The other half is `require_connect_intent`, which runs before anything resolves the
credential -- so `user` there is only whoever the browser is signed in as.

    >>> from voteit.organisation.pipeline import require_connect_intent

    >>> def coming_back(session, uid="a-new-sub", user=None):
    ...     request = RequestFactory().get("/complete/scoutid/")
    ...     request.session = session
    ...     returning = ScoutIDOpenIdConnect(
    ...         strategy=DjangoStrategy(DjangoStorage, request=request)
    ...     )
    ...     returning.__dict__["organisation"] = org
    ...     return require_connect_intent(returning, uid, user=user)

With the intent recorded, the credential goes on the account they are signed in to.

    >>> coming_back({CONNECT_INTENT_SESSION_KEY: "scoutid"}, user=existing) is None
    True

Without it, somebody else is at an open session on a shared computer. Dropping the
session user turns this back into the fresh login it really is, and
`django.contrib.auth` flushes the session when a different person signs in.

    >>> coming_back({}, user=existing)
    {'user': None}

The flag is spent on the login it was meant for, so it cannot wave through a later
one nobody asked for.

    >>> session = {CONNECT_INTENT_SESSION_KEY: "scoutid"}
    >>> coming_back(session, user=existing) is None
    True
    >>> session
    {}

A credential the account already holds is an ordinary re-login, and whose it is
stays `social_user`'s business.

    >>> known = existing.social_auth.create(
    ...     provider="scoutid", uid="a-known-sub", extra_data={}
    ... )
    >>> coming_back({}, uid="a-known-sub", user=existing) is None
    True

Nobody signed in, nothing to protect.

    >>> coming_back({}) is None
    True
