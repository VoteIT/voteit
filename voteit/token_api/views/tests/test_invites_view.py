from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from voteit.invites.models import MeetingInvite
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.organisation.models import Organisation
from voteit.token_api.models import MeetingAPIKey
from voteit.token_api.models import create_api_key_user

User = get_user_model()

LIST_URL = "token-api:invites-list"
DETAIL_URL = "token-api:invites-detail"
ADD_ROLES_URL = "token-api:invites-add-roles"
REMOVE_ROLES_URL = "token-api:invites-remove-roles"


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

    # --- list filters ---

    def _filtered_emails(self, params):
        _, key = self._create_key(scopes=["invites.list"])
        self._api_key_client(key)
        response = self.client.get(reverse(LIST_URL), params)
        self.assertEqual(response.status_code, 200, response.json())
        return {item["user_data"]["email"] for item in response.json()}

    def _create_filter_invites(self):
        # self.invite is test@example.com with participant only
        self.meeting.invites.create(
            user_data={"email": "prop@example.com"},
            roles=[ROLE_PARTICIPANT, ROLE_PROPOSER],
        )
        self.meeting.invites.create(
            user_data={"email": "mod@example.com"},
            roles=[ROLE_PARTICIPANT, ROLE_MODERATOR],
        )

    def test_list_filter_email_is_normalised(self):
        self._create_filter_invites()
        self.assertEqual(
            {"prop@example.com"}, self._filtered_emails({"email": " Prop@Example.com"})
        )

    def test_list_filter_roles(self):
        self._create_filter_invites()
        self.assertEqual(
            {"prop@example.com"}, self._filtered_emails({"roles": ROLE_PROPOSER})
        )
        self.assertEqual(
            {"test@example.com", "prop@example.com", "mod@example.com"},
            self._filtered_emails({"roles": ROLE_PARTICIPANT}),
        )

    def test_list_filter_state(self):
        self._create_filter_invites()
        self.meeting.invites.create(
            user_data={"email": "revoked@example.com"},
            roles=[ROLE_PARTICIPANT],
            state="revoked",
        )
        self.meeting.invites.create(
            user_data={"email": "expired@example.com"},
            roles=[ROLE_PARTICIPANT],
            state="expired",
        )
        self.assertEqual(
            {"revoked@example.com"}, self._filtered_emails({"state": "revoked"})
        )
        self.assertEqual(
            {"revoked@example.com", "expired@example.com"},
            self._filtered_emails({"state": "revoked,expired"}),
        )
        self.assertEqual(
            {"prop@example.com"},
            self._filtered_emails({"state": "open", "roles": ROLE_PROPOSER}),
        )

    def test_list_filter_invalid_state(self):
        _, key = self._create_key(scopes=["invites.list"])
        self._api_key_client(key)
        response = self.client.get(reverse(LIST_URL), {"state": "open,boo"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("state", response.json())

    def test_list_filter_comma_separated_matches_any(self):
        self._create_filter_invites()
        self.assertEqual(
            {"prop@example.com", "mod@example.com"},
            self._filtered_emails({"roles": f"{ROLE_PROPOSER},{ROLE_MODERATOR}"}),
        )

    def test_list_filter_different_params_must_all_match(self):
        self._create_filter_invites()
        self.assertEqual(
            set(),
            self._filtered_emails(
                {"email": "test@example.com", "roles": ROLE_PROPOSER}
            ),
        )
        self.assertEqual(
            {"prop@example.com"},
            self._filtered_emails(
                {"email": "test@example.com,prop@example.com", "roles": "pr"}
            ),
        )

    def test_list_filter_empty_value_is_ignored(self):
        self._create_filter_invites()
        self.assertEqual(
            {"test@example.com", "prop@example.com", "mod@example.com"},
            self._filtered_emails({"email": "", "roles": ""}),
        )

    def test_list_filter_excludes_other_meetings(self):
        other_meeting = self.org.meetings.create(title="Other meeting")
        other_meeting.invites.create(
            user_data={"email": "test@example.com"}, roles=[ROLE_PARTICIPANT]
        )
        _, key = self._create_key(scopes=["invites.list"])
        self._api_key_client(key)
        response = self.client.get(reverse(LIST_URL), {"email": "test@example.com"})
        self.assertEqual([self.invite.pk], [item["pk"] for item in response.json()])

    def test_list_filter_invalid_values(self):
        _, key = self._create_key(scopes=["invites.list"])
        self._api_key_client(key)
        response = self.client.get(
            reverse(LIST_URL), {"email": "not-an-email", "roles": "pa,boo"}
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(["'not-an-email' is not a valid email."], data["email"])
        self.assertIn("roles", data)

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

    # --- Moderator role is off limits ---

    def test_create_rejects_moderator_role(self):
        _, key = self._create_key(scopes=["invites.create"])
        self._api_key_client(key)
        response = self.client.post(
            reverse(LIST_URL),
            {
                "roles": [ROLE_PARTICIPANT, ROLE_MODERATOR],
                "data": [{"email": "new@example.com"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("roles", response.json())
        self.assertFalse(
            MeetingInvite.objects.filter(user_data__email="new@example.com").exists()
        )

    def test_create_rejects_changing_moderator_invite(self):
        _, key = self._create_key(scopes=["invites.create"])
        self._api_key_client(key)
        invite = self.meeting.invites.create(
            user_data={"email": "mod@example.com"},
            roles=[ROLE_PARTICIPANT, ROLE_MODERATOR],
        )
        response = self.client.post(
            reverse(LIST_URL),
            {"roles": [ROLE_PARTICIPANT], "data": [{"email": "mod@example.com"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("roles", response.json())
        invite.refresh_from_db()
        self.assertIn(ROLE_MODERATOR, invite.roles)

    def test_create_rejects_removing_moderator_from_user(self):
        _, key = self._create_key(scopes=["invites.create"])
        self._api_key_client(key)
        moderator = User.objects.get(username="moderator")
        # The invite doesn't carry the moderator role, the user does.
        invite = self.meeting.invites.create(
            user_data={"email": "mod@example.com"}, roles=[ROLE_PARTICIPANT]
        )
        invite.accept(moderator)
        invite.save()
        response = self.client.post(
            reverse(LIST_URL),
            {
                "roles": [ROLE_PARTICIPANT, ROLE_PROPOSER],
                "data": [{"email": "mod@example.com"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("roles", response.json())
        self.assertIn(ROLE_MODERATOR, self.meeting.get_roles(moderator))

    # --- add / remove roles ---

    def _post_roles(self, url_name, invite, roles, scopes=("invites.*",)):
        _, key = self._create_key(scopes=list(scopes))
        self._api_key_client(key)
        return self.client.post(
            reverse(url_name, args=[invite.pk]), {"roles": roles}, format="json"
        )

    def test_add_roles(self):
        response = self._post_roles(ADD_ROLES_URL, self.invite, [ROLE_PROPOSER])
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(self.invite.pk, response.json()["pk"])
        self.assertEqual([ROLE_PARTICIPANT, ROLE_PROPOSER], response.json()["roles"])
        self.invite.refresh_from_db()
        self.assertEqual([ROLE_PARTICIPANT, ROLE_PROPOSER], self.invite.roles)

    def test_add_roles_adds_required_roles(self):
        invite = self.meeting.invites.create(
            user_data={"email": "pv@example.com"}, roles=[ROLE_POTENTIAL_VOTER]
        )
        response = self._post_roles(ADD_ROLES_URL, invite, [ROLE_PROPOSER])
        self.assertEqual(response.status_code, 200, response.json())
        invite.refresh_from_db()
        self.assertEqual(
            [ROLE_PARTICIPANT, ROLE_PROPOSER, ROLE_POTENTIAL_VOTER], invite.roles
        )

    def test_add_roles_updates_user(self):
        self.invite.accept(self.participant)
        self.invite.save()
        response = self._post_roles(ADD_ROLES_URL, self.invite, [ROLE_PROPOSER])
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(
            {ROLE_PARTICIPANT, ROLE_PROPOSER}, self.meeting.get_roles(self.participant)
        )

    def test_remove_roles_updates_user(self):
        invite = self.meeting.invites.create(
            user_data={"email": "x@example.com"},
            roles=[ROLE_PARTICIPANT, ROLE_PROPOSER],
        )
        invite.accept(self.participant)
        invite.save()
        self.assertEqual(
            {ROLE_PARTICIPANT, ROLE_PROPOSER}, self.meeting.get_roles(self.participant)
        )
        response = self._post_roles(REMOVE_ROLES_URL, invite, [ROLE_PROPOSER])
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual([ROLE_PARTICIPANT], response.json()["roles"])
        self.assertEqual({ROLE_PARTICIPANT}, self.meeting.get_roles(self.participant))

    def test_remove_roles_not_on_invite_changes_nothing(self):
        response = self._post_roles(REMOVE_ROLES_URL, self.invite, [ROLE_PROPOSER])
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual([ROLE_PARTICIPANT], response.json()["roles"])

    def test_remove_roles_must_keep_one_role(self):
        invite = self.meeting.invites.create(
            user_data={"email": "x@example.com"},
            roles=[ROLE_PARTICIPANT, ROLE_PROPOSER],
        )
        # Proposer requires participant, so both would go
        response = self._post_roles(REMOVE_ROLES_URL, invite, [ROLE_PARTICIPANT])
        self.assertEqual(response.status_code, 400)
        self.assertIn("roles", response.json())
        invite.refresh_from_db()
        self.assertEqual([ROLE_PARTICIPANT, ROLE_PROPOSER], invite.roles)

    def test_change_roles_rejects_moderator_role(self):
        for url_name in (ADD_ROLES_URL, REMOVE_ROLES_URL):
            with self.subTest(url_name=url_name):
                response = self._post_roles(url_name, self.invite, [ROLE_MODERATOR])
                self.assertEqual(response.status_code, 400)
                self.assertIn("roles", response.json())
        self.invite.refresh_from_db()
        self.assertEqual([ROLE_PARTICIPANT], self.invite.roles)

    def test_change_roles_rejects_moderator_invite(self):
        invite = self.meeting.invites.create(
            user_data={"email": "mod@example.com"},
            roles=[ROLE_PARTICIPANT, ROLE_MODERATOR],
        )
        for url_name in (ADD_ROLES_URL, REMOVE_ROLES_URL):
            with self.subTest(url_name=url_name):
                response = self._post_roles(url_name, invite, [ROLE_PROPOSER])
                self.assertEqual(response.status_code, 400)
                self.assertIn("roles", response.json())
        invite.refresh_from_db()
        self.assertEqual([ROLE_MODERATOR, ROLE_PARTICIPANT], invite.roles)

    def test_change_roles_rejects_invite_accepted_by_moderator(self):
        moderator = User.objects.get(username="moderator")
        # The invite doesn't carry the moderator role, the user does.
        invite = self.meeting.invites.create(
            user_data={"email": "mod@example.com"}, roles=[ROLE_PARTICIPANT]
        )
        invite.accept(moderator)
        invite.save()
        for url_name in (ADD_ROLES_URL, REMOVE_ROLES_URL):
            with self.subTest(url_name=url_name):
                response = self._post_roles(url_name, invite, [ROLE_PROPOSER])
                self.assertEqual(response.status_code, 400)
                self.assertIn("roles", response.json())
        self.assertIn(ROLE_MODERATOR, self.meeting.get_roles(moderator))

    def test_change_roles_invalid_role(self):
        response = self._post_roles(ADD_ROLES_URL, self.invite, ["boo"])
        self.assertEqual(response.status_code, 400)
        self.assertIn("roles", response.json())

    def test_change_roles_requires_roles(self):
        for body in ({}, {"roles": []}):
            with self.subTest(body=body):
                _, key = self._create_key(scopes=["invites.*"])
                self._api_key_client(key)
                response = self.client.post(
                    reverse(ADD_ROLES_URL, args=[self.invite.pk]), body, format="json"
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("roles", response.json())

    def test_change_roles_requires_scope(self):
        for url_name, scope in (
            (ADD_ROLES_URL, "invites.add_roles"),
            (REMOVE_ROLES_URL, "invites.remove_roles"),
        ):
            with self.subTest(url_name=url_name):
                response = self._post_roles(
                    url_name, self.invite, [ROLE_PROPOSER], scopes=["invites.list"]
                )
                self.assertEqual(response.status_code, 403)
                self.assertIn(scope, response.json()["detail"])

    def test_change_roles_specific_scope(self):
        response = self._post_roles(
            ADD_ROLES_URL, self.invite, [ROLE_PROPOSER], scopes=["invites.add_roles"]
        )
        self.assertEqual(response.status_code, 200, response.json())

    def test_change_roles_other_meeting_not_found(self):
        other_meeting = self.org.meetings.create(title="Other meeting")
        invite = other_meeting.invites.create(
            user_data={"email": "other@example.com"}, roles=[ROLE_PARTICIPANT]
        )
        response = self._post_roles(ADD_ROLES_URL, invite, [ROLE_PROPOSER])
        self.assertEqual(response.status_code, 404)
        invite.refresh_from_db()
        self.assertEqual([ROLE_PARTICIPANT], invite.roles)

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
