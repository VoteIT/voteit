from django.test import TestCase
from voteit.organisation.schemas import OAuthTokenSchema


class OrganisationTests(TestCase):
    @property
    def Organisation(self):
        from voteit.organisation.models import Organisation

        return Organisation

    @property
    def Meeting(self):
        from voteit.meeting.models import Meeting

        return Meeting

    def test_meeting_relation(self):
        org = self.Organisation.objects.create()
        meeting = self.Meeting.objects.create(organisation=org)
        self.assertEqual(org, meeting.organisation)


# class AccessTokenTests(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         from voteit.organisation.models import OAuth2Provider
#
#         cls.provider = OAuth2Provider.objects.create(
#             provider_id="idproxy",
#             title="",
#             scopes="hello",
#             client_id="client_id",
#             client_secret="client_secret",
#             redirect_url="https://localhost/",
#             auth_url="https://localhost/",
#             token_url="https://localhost/",
#             identity_url="https://localhost/",
#         )
#
#     @property
#     def _cut(self):
#         from voteit.organisation.models import AccessToken
#
#         return AccessToken
#
#     def test_manager_from_response(self):
#         example_response = OAuthTokenSchema(
#             access_token="123",
#             expires_in=36000,
#             token_type="Bearer",
#             refresh_token="123",
#             scope=["invites"],
#             expires_at=1618295980.7482638,
#         )
#
#         access_token = self._cut.objects.from_response(example_response)
#         breakpoint()
