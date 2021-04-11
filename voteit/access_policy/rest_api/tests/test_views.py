from unittest import mock

import responses
from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase
from voteit.organisation.schemas import OAuthTokenSchema

User = get_user_model()


class MeetingInviteViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.access_policy.models import MeetingInvite
        from voteit.meeting.roles import ROLE_MODERATOR, ROLE_PARTICIPANT

        cls.MeetingInvite = MeetingInvite

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.participant: User = User.objects.create_user("participant")
        cls.moderator: User = User.objects.create_user("moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.invite: MeetingInvite = cls.meeting.invites.create(
            data={"email": "hello@betahaus.net"}, created_by=cls.moderator
        )

    def setUp(self):
        self.invite.refresh_from_db()
        self.participant.refresh_from_db()

    def test_create(self):
        url = reverse("meeting-invites-list")
        data = {"meeting": self.meeting.pk, "data": {"email": "hello@betahaus.net"}}
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
        self.assertEqual(
            response.status_code,
            400,  # Raises invalid transition
        )

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


class UserMatchedInviteViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.access_policy.models import MeetingInvite
        from voteit.meeting.roles import ROLE_MODERATOR
        from voteit.organisation.models import OAuth2Provider
        from voteit.organisation.models import Organisation
        from voteit.access_policy.rest_api.views import UserMatchedInviteViewSet

        cls.organisation = Organisation.objects.create()
        cls.provider = OAuth2Provider.objects.create(
            provider_id="idproxy",
            organisation=cls.organisation,
            client_id="client_id",
            client_secret="client_secret",
            redirect_url="https://voteit.se/dummy",
            auth_url="https://voteit.se/dummy",
            token_url="https://voteit.se/dummy",
            identity_url="https://voteit.se/dummy",
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
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.invite: MeetingInvite = cls.meeting.invites.create(
            data={"email": "hello@betahaus.net"}, created_by=cls.moderator
        )
        cls.invite2: MeetingInvite = cls.meeting.invites.create(
            data={"email": "goodbye@betahaus.net"}, created_by=cls.moderator
        )
        cls.oauth_like = OAuthTokenSchema(
            access_token="123",
            expires_in=3600,
            token_type="bearer",
            scope=["identity", "email"],
            refresh_token="abc",
            expires_at=23487842333,
        )
        UserMatchedInviteViewSet.get_token = mock.MagicMock(return_value=cls.oauth_like)
        cls.mock_api_return = [
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
        ]
        # FIXME:
        url = "http://localhost:8001/service-api/validated-user-data/"
        cls.responses = responses.RequestsMock()
        cls.responses.start()
        cls.responses.add(responses.GET, url, json=cls.mock_api_return)

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
        url = reverse("matched-invites-list")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(1, len(data))
        self.assertEqual(self.invite.pk, data[0]["pk"])

    def test_not_open(self):
        self.invite.revoke()
        self.invite.save()
        self.client.force_login(self.outsider)
        url = reverse("matched-invites-list")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(0, len(data))

    def test_used_invite_retrieve(self):
        # Not currently part of the normal queryset, but can be retrieved if it's used before
        self.invite2.accept(self.outsider)
        self.invite2.save()
        self.client.force_login(self.outsider)
        url = reverse("matched-invites-detail", kwargs={"pk": self.invite2.pk})
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(self.invite2.pk, data["pk"])

    def test_matched_invite_retrieve(self):
        # Can't be fetched although it's usable
        self.client.force_login(self.outsider)
        url = reverse("matched-invites-detail", kwargs={"pk": self.invite.pk})
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

    def test_accept_matched_invite(self):
        self.client.force_login(self.outsider)
        url = reverse("matched-invites-accept", kwargs={"pk": self.invite.pk})
        response = self.client.post(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(self.invite.pk, data["pk"])
        self.assertEqual("accepted", data["state"])

    def test_accept_not_matched(self):
        self.client.force_login(self.outsider)
        url = reverse("matched-invites-accept", kwargs={"pk": self.invite2.pk})
        response = self.client.post(url)
        self.assertEqual(404, response.status_code)

    def test_reject(self):
        self.client.force_login(self.outsider)
        url = reverse("matched-invites-reject", kwargs={"pk": self.invite.pk})
        response = self.client.post(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(self.invite.pk, data["pk"])
        self.assertEqual("rejected", data["state"])

    def test_reject_not_matched(self):
        self.client.force_login(self.outsider)
        url = reverse("matched-invites-reject", kwargs={"pk": self.invite2.pk})
        response = self.client.post(url)
        self.assertEqual(404, response.status_code)
