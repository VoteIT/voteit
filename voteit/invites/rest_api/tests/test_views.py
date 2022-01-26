from __future__ import annotations

from base64 import b64encode
from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

import responses
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils.timezone import now
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.organisation.schemas import OAuthTokenSchema

if TYPE_CHECKING:
    from voteit.core.models import User as UserType

User: UserType = get_user_model()


class MeetingInviteViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.invites.models import MeetingInvite
        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT
        from voteit.organisation.models import Organisation

        cls.MeetingInvite = MeetingInvite

        cls.organisation = Organisation.objects.create()
        cls.meeting: Meeting = cls.organisation.meetings.create(
            title="Test meeting", state="ongoing"
        )
        cls.participant: User = User.objects.create_user("participant")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.invite: MeetingInvite = cls.meeting.invites.create(
            invite_data="hello@betahaus.net", created_by=cls.moderator
        )

    def setUp(self):
        self.invite.refresh_from_db()
        self.participant.refresh_from_db()

    def test_create(self):
        url = reverse("meeting-invites-list")
        data = {
            "meeting": self.meeting.pk,
            "invite_data": "hello@betahaus.net",
        }
        for user, status in (
            (None, 401),
            (self.participant, 403),
            (self.moderator, 201),
        ):
            if user:
                self.client.force_login(user)
            response = self.client.post(url, data)
            self.assertEqual(
                response.status_code,
                status,
                f"{user} action returned wrong response code",
            )

    def test_create_meeting_ne(self):
        url = reverse("meeting-invites-list")
        data = {
            "title": "Stuff",
            "meeting": -1,
        }
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("detail"), "No item found where pk==-1")

    def test_get(self):
        url = reverse("meeting-invites-list")
        data = {
            "meeting": self.meeting.pk,
        }
        self.client.force_login(self.moderator)
        response = self.client.get(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json()))

    def test_transition_moderator(self):
        url = f"/api/meeting-invites/{self.invite.pk}/transitions/"
        data = {"transition": "revoke"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)

    def test_bad_transition_moderator(self):
        url = f"/api/meeting-invites/{self.invite.pk}/transitions/"
        data = {"transition": "wooohoooo"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    def test_transition_unauthorized_users(self):
        url = f"/api/meeting-invites/{self.invite.pk}/transitions/"
        data = {"transition": "revoke"}
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            401,
        )
        self.client.force_login(self.participant)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 403)

    def test_delete(self):
        url = reverse("meeting-invites-detail", kwargs={"pk": self.invite.pk})
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)

    def test_delete_participant(self):
        url = reverse("meeting-invites-detail", kwargs={"pk": self.invite.pk})
        self.client.force_login(self.participant)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_used_invite(self):
        self.invite.accept(self.participant)
        self.invite.save()
        url = reverse("meeting-invites-detail", kwargs={"pk": self.invite.pk})
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 403)

    def test_change(self):
        url = reverse("meeting-invites-detail", kwargs={"pk": self.invite.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, {"roles": ["participant"]})
        self.assertEqual(response.status_code, 200)

    def test_change_used_invite(self):
        self.invite.accept(self.participant)
        self.invite.save()
        url = reverse("meeting-invites-detail", kwargs={"pk": self.invite.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, {"roles": ["participant"]})
        self.assertEqual(response.status_code, 403)


@override_settings(ID_PROXY_API_KEY="xxx")
class MatchInvitesViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.invites.models import MeetingInvite
        from voteit.organisation.models import Organisation

        cls.MeetingInvite = MeetingInvite

        cls.organisation = Organisation.objects.create()
        User.objects.create_user(username="invite_service", password="secret")

        cls.meeting: Meeting = cls.organisation.meetings.create(
            title="Test meeting",
            state="ongoing",  # organisation=cls.organisation
        )
        cls.moderator: User = User.objects.create_user(
            "moderator",  # organisation=cls.organisation
        )
        cls.invite: MeetingInvite = cls.meeting.invites.create(
            invite_data="hello@betahaus.net", created_by=cls.moderator
        )
        cls.invite2: MeetingInvite = cls.meeting.invites.create(
            invite_data="goodbye@betahaus.net", created_by=cls.moderator
        )

    def setUp(self):
        self.invite.refresh_from_db()

    def _mk_auth(self):
        # credentials = "invite_service:secret"
        # encoded = str(b64encode(credentials.encode("utf-8")), "utf-8")
        return {"HTTP_API_KEY": "xxx"}

    def test_authenticated_no_payload(self):
        url = reverse("match-invites-query")
        response = self.client.post(url, **self._mk_auth())
        # Required for query
        self.assertEqual(400, response.status_code)

    def test_validated_email(self):
        payload = [
            {
                "scope": "email",
                "data": "hello@betahaus.net",
                "validated": "2021-03-24T15:56:00.043000Z",
            }
        ]
        url = reverse("match-invites-query")
        response = self.client.post(url, data=payload, **self._mk_auth())
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(1, len(data))
        self.assertEqual(self.invite.pk, data[0]["pk"])

    def test_used_dont_show_up(self):
        self.invite.revoke()
        self.invite.save()
        payload = [
            {
                "scope": "email",
                "data": "hello@betahaus.net",
                "validated": "2021-03-24T15:56:00.043000Z",
            }
        ]
        url = reverse("match-invites-query")
        response = self.client.post(url, data=payload, **self._mk_auth())
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(0, len(data))

    def test_reject(self):
        payload = [
            {
                "scope": "email",
                "data": "hello@betahaus.net",
                "validated": "2021-03-24T15:56:00.043000Z",
            }
        ]
        url = reverse("match-invites-reject", kwargs={"pk": self.invite.pk})
        response = self.client.post(url, data=payload, **self._mk_auth())
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(self.invite.pk, data["pk"])
        self.assertEqual("rejected", data["state"])
        self.invite.refresh_from_db()
        self.assertEqual("rejected", self.invite.state)

    def test_reject_no_match(self):
        payload = [
            {
                "scope": "email",
                "data": "idontexist@betahaus.net",
                "validated": "2021-03-24T15:56:00.043000Z",
            }
        ]
        url = reverse("match-invites-reject", kwargs={"pk": self.invite.pk})
        response = self.client.post(url, data=payload, **self._mk_auth())
        self.assertEqual(404, response.status_code)


class UserMatchedInviteViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.invites.models import MeetingInvite
        from voteit.meeting.roles import ROLE_MODERATOR
        from voteit.organisation.models import OAuth2Provider
        from voteit.organisation.models import Organisation

        cls.organisation = Organisation.objects.create()
        cls.provider = OAuth2Provider.objects.create(
            provider_id="idproxy",
            organisation=cls.organisation,
            client_id="client_id",
            client_secret="client_secret",
            # redirect_url="https://voteit.se/dummy",
            # auth_url="https://voteit.se/dummy",
            # token_url="https://voteit.se/dummy",
            # identity_url="https://voteit.se/dummy",
        )
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing", organisation=cls.organisation
        )
        cls.moderator: User = User.objects.create_user(
            "moderator", organisation=cls.organisation
        )
        cls.outsider: User = User.objects.create_user(
            "outsider", organisation=cls.organisation
        )
        later = now() + timedelta(hours=1)
        token_mod = OAuthTokenSchema(
            access_token="123",
            expires_in=3600,
            scope=["identity", "email"],
            refresh_token="abc",
            expires_at=later,
        )
        token_outsider = OAuthTokenSchema(**token_mod.dict())
        token_outsider.access_token = "1234"
        token_outsider.refresh_token = "abcd"
        cls.mod_access_token = cls.moderator.access_tokens.create_from_pydantic(
            token_mod, provider=cls.provider, user=cls.moderator
        )
        cls.outsider_access_token = cls.outsider.access_tokens.create_from_pydantic(
            token_outsider, provider=cls.provider, user=cls.outsider
        )
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.invite: MeetingInvite = cls.meeting.invites.create(
            invite_data="hello@betahaus.net", created_by=cls.moderator
        )
        cls.invite2: MeetingInvite = cls.meeting.invites.create(
            invite_data="goodbye@betahaus.net", created_by=cls.moderator
        )

        cls.mock_api_return = {
            "pk": 1,
            "application": 1,
            "given_name": "Hello",
            "family_name": "Is it me you are looking for?",
            "identity_id": "123",
            "user_data": [
                {
                    "pk": 1,
                    "scope": "email",
                    "data": "hello@betahaus.net",
                    "validated": "2021-03-24T15:56:00.043000Z",
                },
                {
                    "pk": 2,
                    "scope": "cell_phone",
                    "data": "+123-123-123",
                    "validated": "2021-03-24T15:56:00.043000Z",
                },
            ],
        }

        cls.responses = responses.RequestsMock()
        cls.responses.start()
        cls.responses.add(
            responses.GET, cls.provider.identity_url, json=cls.mock_api_return
        )

    def setUp(self):
        self.invite.refresh_from_db()
        self.invite2.refresh_from_db()

    @classmethod
    def tearDownClass(cls):
        cls.responses.stop()
        cls.responses.reset()
        super().tearDownClass()

    def test_match(self):
        self.client.force_login(self.outsider)
        url = reverse("handle-matched-invites-list")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(1, len(data))
        self.assertEqual(self.invite.pk, data[0]["pk"])

    def test_not_open(self):
        self.invite.revoke()
        self.invite.save()
        self.client.force_login(self.outsider)
        url = reverse("handle-matched-invites-list")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(0, len(data))

    def test_accept_matched_invite(self):
        self.client.force_login(self.outsider)
        url = reverse("handle-matched-invites-accept", kwargs={"pk": self.invite.pk})
        response = self.client.post(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(self.invite.pk, data["pk"])
        self.assertEqual("accepted", data["state"])
        self.invite.refresh_from_db()
        self.assertEqual("accepted", self.invite.state)

    def test_accept_not_matched(self):
        self.client.force_login(self.outsider)
        url = reverse("handle-matched-invites-accept", kwargs={"pk": self.invite2.pk})
        response = self.client.post(url)
        self.assertEqual(404, response.status_code)

    def test_reject(self):
        self.client.force_login(self.outsider)
        url = reverse("handle-matched-invites-reject", kwargs={"pk": self.invite.pk})
        response = self.client.post(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(self.invite.pk, data["pk"])
        self.assertEqual("rejected", data["state"])

    def test_reject_not_matched(self):
        self.client.force_login(self.outsider)
        url = reverse("handle-matched-invites-reject", kwargs={"pk": self.invite2.pk})
        response = self.client.post(url)
        self.assertEqual(404, response.status_code)

    def test_match_organisation(self):
        from voteit.organisation.models import Organisation

        org = Organisation.objects.create()
        meeting = org.meetings.create()
        meeting.invites.create(
            invite_data="hello@betahaus.net", created_by=self.moderator
        )

        self.client.force_login(self.outsider)
        url = reverse("handle-matched-invites-list")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(1, len(data))
        self.assertEqual(self.invite.pk, data[0]["pk"])

    def test_no_organisation(self):
        self.client.force_login(User.objects.create_user('virginia'))
        url = reverse("handle-matched-invites-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)
