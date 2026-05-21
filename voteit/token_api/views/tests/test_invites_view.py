from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.invites.models import MeetingInvite
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.organisation.models import Organisation
from voteit.token_api.models import MeetingAPIKey
from voteit.token_api.models import create_api_key_user

User = get_user_model()

LIST_URL = "token-api:invites-list"
DETAIL_URL = "token-api:invites-detail"


class InvitesViewTest(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.get(pk=1)
        cls.meeting = cls.org.meetings.get(pk=1)
        cls.participant = User.objects.get(username="participant")
        cls.invite = cls.meeting.invites.create(
            user_data={"email": "test@example.com"},
            roles=[ROLE_PARTICIPANT],
        )

    def setUp(self):
        self.invite.refresh_from_db()

    def _create_key(self, scopes):
        api_user = create_api_key_user(self.meeting)
        obj, key = MeetingAPIKey.objects.create_key(
            name="Test key",
            scopes=scopes,
            meeting=self.meeting,
            user=api_user,
        )
        return obj, key

    def _api_key_client(self, key: str):
        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key {key}")

    # --- list ---

    def test_list_returns_invites_for_meeting(self):
        _, key = self._create_key(scopes=["invites.list"])
        self._api_key_client(key)
        response = self.client.get(reverse(LIST_URL))
        self.assertEqual(response.status_code, 200)
        pks = [item["pk"] for item in response.json()]
        self.assertIn(self.invite.pk, pks)

    def test_list_requires_scope(self):
        _, key = self._create_key(scopes=["meeting.list"])
        self._api_key_client(key)
        response = self.client.get(reverse(LIST_URL))
        self.assertEqual(response.status_code, 403)
        self.assertIn("invites.list", response.json()["detail"])
        self.assertIn("invites.*", response.json()["detail"])

    def test_list_unauthenticated_returns_403(self):
        response = self.client.get(reverse(LIST_URL))
        self.assertEqual(response.status_code, 403)

    def test_list_session_auth_returns_empty(self):
        self.client.force_login(self.participant)
        response = self.client.get(reverse(LIST_URL))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    # --- retrieve ---

    def test_retrieve_returns_invite(self):
        _, key = self._create_key(scopes=["invites.retrieve"])
        self._api_key_client(key)
        response = self.client.get(reverse(DETAIL_URL, args=[self.invite.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pk"], self.invite.pk)

    def test_retrieve_requires_scope(self):
        _, key = self._create_key(scopes=["invites.list"])
        self._api_key_client(key)
        response = self.client.get(reverse(DETAIL_URL, args=[self.invite.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertIn("invites.retrieve", response.json()["detail"])
        self.assertIn("invites.*", response.json()["detail"])

    # --- create ---

    def test_create_invite_sets_meeting_from_api_key(self):
        _, key = self._create_key(scopes=["invites.create"])
        self._api_key_client(key)
        response = self.client.post(
            reverse(LIST_URL),
            {
                "roles": [str(ROLE_PARTICIPANT)],
                "data": [{"email": "new@example.com"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        invite = MeetingInvite.objects.get(user_data__email="new@example.com")
        self.assertEqual(invite.meeting_id, self.meeting.pk)

    def test_create_does_not_accept_meeting_field(self):
        _, key = self._create_key(scopes=["invites.create"])
        self._api_key_client(key)
        other_meeting = self.org.meetings.create(title="Other meeting")
        response = self.client.post(
            reverse(LIST_URL),
            {
                "meeting": other_meeting.pk,
                "roles": [str(ROLE_PARTICIPANT)],
                "data": [{"email": "hijack@example.com"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(
            MeetingInvite.objects.filter(
                user_data__email="hijack@example.com", meeting=other_meeting
            ).exists()
        )

    def test_create_dryrun_does_not_persist(self):
        _, key = self._create_key(scopes=["invites.create"])
        self._api_key_client(key)
        count_before = MeetingInvite.objects.filter(meeting=self.meeting).count()
        response = self.client.post(
            reverse(LIST_URL),
            {
                "roles": [str(ROLE_PARTICIPANT)],
                "data": [{"email": "dryrun@example.com"}],
                "dryrun": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            MeetingInvite.objects.filter(meeting=self.meeting).count(), count_before
        )

    def test_create_requires_scope(self):
        _, key = self._create_key(scopes=["invites.list"])
        self._api_key_client(key)
        response = self.client.post(
            reverse(LIST_URL),
            {"roles": [str(ROLE_PARTICIPANT)], "data": [{"email": "x@example.com"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("invites.create", response.json()["detail"])
        self.assertIn("invites.*", response.json()["detail"])

    # --- Effects on users ---

    def test_create_causes_used_invites_to_update_user(self):
        _, key = self._create_key(scopes=["invites.*"])
        self._api_key_client(key)
        # By manipulating this invite, the users permission should change.
        invite = self.meeting.invites.create(
            user_data={"email": "x@example.com"}, roles=[ROLE_PARTICIPANT]
        )
        invite.accept(self.participant)
        invite.save()
        response = self.client.post(
            reverse(LIST_URL),
            {
                "roles": [ROLE_PARTICIPANT, ROLE_PROPOSER],
                "data": [{"email": "x@example.com"}],
            },
            format="json",
        )
        data = response.json()
        self.assertEqual(response.status_code, 201, data)
        self.assertEqual(
            data,
            {
                "data": [{"email": "x@example.com"}],
                "dryrun": False,
                "roles": [ROLE_PARTICIPANT, ROLE_PROPOSER],
            },
        )
        self.assertEqual(
            {ROLE_PARTICIPANT, ROLE_PROPOSER}, self.meeting.get_roles(self.participant)
        )

    def test_delete_invite_user_effect(self):
        # We may want to change the effect of deleting an invite later on. This test will catch that.
        _, key = self._create_key(scopes=["invites.*"])
        self._api_key_client(key)
        # By manipulating this invite, the users permission should change.
        invite = self.meeting.invites.create(
            user_data={"email": "x@example.com"}, roles=[ROLE_PARTICIPANT]
        )
        invite.accept(self.participant)
        invite.save()
        response = self.client.delete(reverse(DETAIL_URL, args=[self.invite.pk]))
        self.assertEqual(response.status_code, 204)
        # No effect
        self.assertEqual({ROLE_PARTICIPANT}, self.meeting.get_roles(self.participant))

    # --- auditlog ---

    def test_create_fetched_by_auditlog(self):
        obj, key = self._create_key(scopes=["invites.*"])
        self._api_key_client(key)
        response = self.client.post(
            reverse(LIST_URL),
            {
                "roles": [ROLE_PARTICIPANT, ROLE_PROPOSER],
                "data": [{"email": "x@example.com"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        invite = MeetingInvite.objects.get(user_data__email="x@example.com")

        logentry = LogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(MeetingInvite),
            object_id=invite.pk,
            actor=obj.user,
        ).first()

        self.assertIsNotNone(
            logentry,
            "No LogEntry found for the created invite with the API key user as actor",
        )
        self.assertEqual(logentry.actor, obj.user)
        self.assertEqual(logentry.object_id, invite.pk)
