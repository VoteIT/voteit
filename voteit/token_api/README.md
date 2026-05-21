# Token API

The token API lets external services interact with a meeting's resources using
long-lived API keys. Each key is bound to one meeting and carries a list of
permission scopes that control what the key can do.

## Creating a key

Keys are issued via the Django admin or the REST API (meeting moderators only).
They can also be created directly at the model level:

    >>> from voteit.organisation.models import Organisation
    >>> org = Organisation.objects.create(title="Test Org")
    >>> meeting = org.meetings.create(title="Annual Meeting")

    >>> from voteit.token_api.models import MeetingAPIKey, create_api_key_user
    >>> api_user = create_api_key_user(meeting)
    >>> key_obj, raw_key = MeetingAPIKey.objects.create_key(
    ...     name="Integration key",
    ...     scopes=["invites.*"],
    ...     meeting=meeting,
    ...     user=api_user,
    ... )

The raw key is returned only at creation time — store it securely, it cannot be
retrieved again. It consists of a public prefix and a secret part joined by `.`:

    >>> "." in raw_key
    True

## Authenticating requests

Pass the raw key in the `Authorization` header as `Api-Key <key>`:

    >>> from rest_framework.test import APIClient
    >>> from rest_framework.reverse import reverse
    >>> client = APIClient()
    >>> client.credentials(HTTP_AUTHORIZATION=f"Api-Key {raw_key}")
    >>> response = client.get(reverse("token-api:invites-list"))
    >>> response.status_code
    200

An unauthenticated request is rejected:

    >>> APIClient().get(reverse("token-api:invites-list")).status_code
    403

## Scopes

Scopes follow the pattern `resource.action` or `resource.*`. A key is rejected
with 403 when it lacks the required scope, and the response tells the caller
exactly which scope is needed:

    >>> limited_obj, limited_key = MeetingAPIKey.objects.create_key(
    ...     name="Read-only key",
    ...     scopes=["meeting.list"],
    ...     meeting=meeting,
    ...     user=create_api_key_user(meeting),
    ... )
    >>> client.credentials(HTTP_AUTHORIZATION=f"Api-Key {limited_key}")
    >>> response = client.post(
    ...     reverse("token-api:invites-list"),
    ...     {"roles": ["pa"], "data": [{"email": "x@example.com"}]},
    ...     format="json",
    ... )
    >>> response.status_code
    403
    >>> "invites.create" in response.json()["detail"]
    True

Wildcard scopes (`resource.*`) cover all actions for a resource. Redundant
specific scopes are normalised away on save:

    >>> from voteit.token_api.validators import normalize_scopes
    >>> normalize_scopes(["invites.*", "invites.list", "meeting.list"])
    ['invites.*', 'meeting.list']

## Revoking a key

Call `DELETE /api/meeting-api-token/{prefix}/` as a meeting moderator.
The key is marked revoked but not deleted from the database.

    >>> from voteit.meeting.roles import ROLE_PARTICIPANT, ROLE_MODERATOR
    >>> moderator = org.users.create(username="moderator_user")
    >>> meeting.add_roles(moderator, ROLE_PARTICIPANT, ROLE_MODERATOR)
    {...}
    >>> mod_client = APIClient()
    >>> mod_client.force_login(moderator)
    >>> response = mod_client.delete(reverse("meeting-api-token-detail", args=[key_obj.prefix]))
    >>> response.status_code
    204

The key is rejected immediately after revocation:

    >>> client.credentials(HTTP_AUTHORIZATION=f"Api-Key {raw_key}")
    >>> client.get(reverse("token-api:invites-list")).status_code
    403
