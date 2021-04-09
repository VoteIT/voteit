from unittest import mock

from django.contrib.auth import get_user_model
from requests import Response
from requests_oauthlib import OAuth2Session
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


# class UserMatchedInviteViewSetTests(APITestCase):
#     @classmethod
#     def setUpTestData(cls):
#         from voteit.meeting.models import Meeting
#         from voteit.access_policy.models import MeetingInvite
#         from voteit.meeting.roles import ROLE_MODERATOR
#         from voteit.organisation.models import OAuth2Provider
#         from voteit.organisation.models import Organisation
#         from voteit.access_policy.rest_api.views import UserMatchedInviteViewSet
#
#         cls.organisation = Organisation.objects.create()
#         cls.provider = OAuth2Provider.objects.create(
#             provider_id="idproxy",
#             organisation=cls.organisation,
#             client_id="client_id",
#             client_secret="client_secret",
#             redirect_url="https://voteit.se/dummy",
#             auth_url="https://voteit.se/dummy",
#             token_url="https://voteit.se/dummy",
#             identity_url="https://voteit.se/dummy",
#         )
#
#         cls.meeting: Meeting = Meeting.objects.create(
#             title="Test meeting", state="ongoing", organisation=cls.organisation
#         )
#         # cls.participant: User = User.objects.create_user("participant")
#         cls.moderator: User = User.objects.create_user(
#             "moderator", organisation=cls.organisation
#         )
#         cls.outsider: User = User.objects.create_user(
#             "outsider", organisation=cls.organisation
#         )
#         # cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
#         cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
#         cls.invite: MeetingInvite = cls.meeting.invites.create(
#             data={"email": "hello@betahaus.net"}, created_by=cls.moderator
#         )
#         cls.invite2: MeetingInvite = cls.meeting.invites.create(
#             data={"email": "goodbye@betahaus.net"}, created_by=cls.moderator
#         )
#         cls.oauth_like = OAuthTokenSchema(
#             access_token="123",
#             expires_in=3600,
#             token_type="bearer",
#             scope=["identity", "email"],
#             refresh_token="abc",
#             expires_at=234878433,
#         )
#         UserMatchedInviteViewSet.get_token = mock.MagicMock(return_value=cls.oauth_like)
#         mock_api_return = [
#             {
#                 "pk": 1,
#                 "scope": "email",
#                 "data": "hello@betahaus.net",
#                 "validated": "2021-03-24T15:56:00.043000Z",
#             },
#             {
#                 "pk": 2,
#                 "scope": "cell_phone",
#                 "data": "+123-123-123",
#                 "validated": "2021-03-24T15:56:00.043000Z",
#             },
#         ]
#         response = Response()
#         response.content = mock_api_return
#         OAuth2Session.get = mock.MagicMock(return_value=response)
#         # OAuth2Session.get.return_value.ok = True
#         # return_value=mock_api_return
#
#     def setUp(self):
#         self.invite.refresh_from_db()
#         # OAuth2Session.get.reset_mock()
#
#     # def test_some_func(self, mock_api_call):
#     #     mock_api_call.return_value = MagicMock(
#     #         status_code=200, response=json.dumps({"key": "value"})
#     #     )
#
#     def test_match(self):
#         self.client.force_login(self.outsider)
#         url = reverse("matched-invites-list")
#         response = self.client.get(url)
#         self.assertEqual(200, response.status_code)
#         breakpoint()
#
#     def test_not_open(self):
#         pass
#
#     def test_used_invite(self):
#         pass
#
#     def test_accept(self):
#         pass
#
#     def test_reject(self):
#         pass
