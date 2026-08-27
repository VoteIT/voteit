from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from voteit.messaging.testing import testing_channel_layers_setting
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase
from social_django.models import UserSocialAuth

from voteit.invites.channels import MeetingInvitesChannel
from voteit.invites.messages import MeetingInviteChanged
from voteit.invites.models import MeetingGroupAnnotation
from voteit.invites.models import MeetingInvite
from voteit.invites.statemachines import InviteStateMachine
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation.models import Organisation

if TYPE_CHECKING:
    from voteit.core.models import User as UserType

User: UserType = get_user_model()


class MeetingInviteViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.organisation: Organisation = Organisation.objects.get(pk=1)
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.participant: User = cls.meeting.participants.get(username="participant")
        cls.moderator: User = cls.meeting.participants.get(username="moderator")
        cls.outsider: User = User.objects.create_user("outsider")
        cls.invite: MeetingInvite = cls.meeting.invites.create(
            user_data={"email": "hello@betahaus.net"},
        )

    def setUp(self):
        self.invite.refresh_from_db()
        self.participant.refresh_from_db()

    def test_transition_moderator(self):
        url = reverse("meeting-invites-event", kwargs={"pk": self.invite.pk})
        data = {"event": "revoke"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

    def test_bad_transition_moderator(self):
        url = reverse("meeting-invites-event", kwargs={"pk": self.invite.pk})
        data = {"event": "woho"}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)

    def test_transition_unauthorized_users(self):
        url = reverse("meeting-invites-event", kwargs={"pk": self.invite.pk})
        data = {"event": "revoke"}
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code,
            401,
        )
        self.client.force_login(self.participant)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 404)

    def test_delete(self):
        url = reverse("meeting-invites-detail", kwargs={"pk": self.invite.pk})
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)

    def test_delete_participant(self):
        url = reverse("meeting-invites-detail", kwargs={"pk": self.invite.pk})
        self.client.force_login(self.participant)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 404)

    def test_delete_used_invite(self):
        self.invite.accept(self.participant)
        self.invite.save()
        url = reverse("meeting-invites-detail", kwargs={"pk": self.invite.pk})
        self.client.force_login(self.moderator)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)

    def test_change(self):
        url = reverse("meeting-invites-detail", kwargs={"pk": self.invite.pk})
        self.client.force_login(self.moderator)
        response = self.client.patch(url, {"roles": ["participant"]})
        self.assertEqual(response.status_code, 405)

    def test_bulk_revoke(self):
        url = reverse("meeting-invites-bulk-revoke")
        data = {"meeting": self.meeting.pk, "invites": [self.invite.pk]}
        self.client.force_login(self.moderator)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"revoked": 1})
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.state, InviteStateMachine.revoked.id)

    def test_annotations(self):
        grp = self.meeting.groups.create()
        self.invite.group_annotations.create(meeting_group=grp)
        url = reverse("meeting-invites-detail", kwargs={"pk": self.invite.pk})
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            {
                "pk": self.invite.pk,
                "annotations": [
                    {"meeting_group": grp.pk, "role": None, "name": "group"}
                ],
            },
            data,
        )


@override_settings(ID_PROXY_API_KEY="xxx")
class MatchInvitesViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
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
            user_data={"email": "hello@betahaus.net"},
        )
        cls.invite2: MeetingInvite = cls.meeting.invites.create(
            user_data={"email": "goodbye@betahaus.net"},
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
        self.invite.revoke(force=True)
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
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.organisation: Organisation = Organisation.objects.get(pk=1)
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing", organisation=cls.organisation
        )
        cls.outsider: User = User.objects.create_user(
            "outsider", organisation=cls.organisation
        )
        cls.invite_matching: MeetingInvite = cls.meeting.invites.create(
            user_data={"email": "hello@betahaus.net"},
        )
        cls.invite_other: MeetingInvite = cls.meeting.invites.create(
            user_data={"email": "goodbye@betahaus.net"},
        )
        cls.usa: UserSocialAuth = cls.outsider.social_auth.create(
            provider=IDPROXY_PROVIDER,
            uid="abc",
            extra_data={"user_data": {"email": ["hello@betahaus.net"]}},
        )

    def test_match(self):
        self.client.force_login(self.outsider)
        url = reverse("handle-matched-invites-list")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(1, len(data))
        self.assertEqual(self.invite_matching.pk, data[0]["pk"])

    def test_not_open(self):
        self.invite_matching.revoke(force=True)
        self.invite_matching.save()
        self.client.force_login(self.outsider)
        url = reverse("handle-matched-invites-list")
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(200, response.status_code, data)
        self.assertEqual(0, len(data))

    def test_accept_matched_invite(self):
        self.client.force_login(self.outsider)
        url = reverse(
            "handle-matched-invites-accept", kwargs={"pk": self.invite_matching.pk}
        )
        response = self.client.post(url)
        data = response.json()
        self.assertEqual(200, response.status_code, data)
        self.assertEqual(self.invite_matching.pk, data["pk"])
        self.assertEqual("accepted", data["state"])
        self.invite_matching.refresh_from_db()
        self.assertEqual("accepted", self.invite_matching.state)

    def test_accept_not_matched(self):
        self.client.force_login(self.outsider)
        url = reverse(
            "handle-matched-invites-accept", kwargs={"pk": self.invite_other.pk}
        )
        response = self.client.post(url)
        self.assertEqual(404, response.status_code)

    def test_reject(self):
        self.client.force_login(self.outsider)
        url = reverse(
            "handle-matched-invites-reject", kwargs={"pk": self.invite_matching.pk}
        )
        response = self.client.post(url)
        data = response.json()
        self.assertEqual(200, response.status_code, data)
        self.assertEqual(self.invite_matching.pk, data["pk"])
        self.assertEqual("rejected", data["state"])

    def test_reject_not_matched(self):
        self.client.force_login(self.outsider)
        url = reverse(
            "handle-matched-invites-reject", kwargs={"pk": self.invite_other.pk}
        )
        response = self.client.post(url)
        self.assertEqual(404, response.status_code)

    def test_match_organisation(self):
        org = Organisation.objects.create()
        meeting = org.meetings.create()
        # Won't match
        meeting.invites.create(
            user_data={"email": "hello@betahaus.net"},
        )
        self.client.force_login(self.outsider)
        url = reverse("handle-matched-invites-list")
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(200, response.status_code, data)
        self.assertEqual(1, len(data))
        self.assertEqual(self.invite_matching.pk, data[0]["pk"])

    def test_no_organisation(self):
        self.client.force_login(User.objects.create_user("virginia"))
        url = reverse("handle-matched-invites-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)


class MeetingInviteViewSetCreateTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.organisation: Organisation = Organisation.objects.get(pk=1)
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.participant: User = cls.meeting.participants.get(username="participant")
        cls.moderator: User = cls.meeting.participants.get(username="moderator")
        cls.group = MeetingGroup.objects.create(
            meeting=cls.meeting, groupid="committee"
        )

    def _url(self):
        return reverse("meeting-invites-list")

    def tearDown(self):
        cache.clear()

    def _post(self, data, user=None):
        if user is None:
            user = self.moderator
        self.client.force_login(user)
        return self.client.post(self._url(), data, content_type="application/json")

    def test_create_single(self):
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"email": "new@example.com"}],
            }
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["invites"]["added"], 1)
        self.assertEqual(data["invites"]["changed"], 0)
        self.assertEqual(data["invites"]["existed"], 0)
        self.assertTrue(
            self.meeting.invites.filter(user_data={"email": "new@example.com"}).exists()
        )

    def test_create_multiple(self):
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"email": "a@example.com"}, {"email": "b@example.com"}],
            }
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["invites"]["added"], 2)

    def test_create_duplicate(self):
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"email": "a@example.com"}, {"email": "a@example.com"}],
            }
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["invites"]["added"], 1)

    def test_create_duplicate_with_group(self):
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [
                    {"email": "a@example.com", "group": self.group.groupid},
                    {"email": "a@example.com", "group": self.group.groupid},
                ],
            }
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["invites"]["added"], 1)

    def test_create_existing_unchanged(self):
        self.meeting.invites.create(
            user_data={"email": "existing@example.com"}, roles=["pa"]
        )
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"email": "existing@example.com"}],
            }
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["invites"]["added"], 0)
        self.assertEqual(data["invites"]["existed"], 1)

    def test_create_role_change(self):
        self.meeting.invites.create(
            user_data={"email": "change@example.com"}, roles=["pa"]
        )
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa", "mo"],
                "data": [{"email": "change@example.com"}],
            }
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["invites"]["changed"], 1)

    def test_create_unauthenticated(self):
        response = self.client.post(
            self._url(),
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"email": "x@example.com"}],
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_create_non_moderator(self):
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"email": "x@example.com"}],
            },
            user=self.participant,
        )
        self.assertIn(response.status_code, (400, 403, 404))

    def test_create_unknown_user_data_key(self):
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"unknown_key": "value"}],
            }
        )
        self.assertEqual(response.status_code, 400)

    def test_create_invalid_email(self):
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"email": "not-an-email"}],
            }
        )
        self.assertEqual(response.status_code, 400)

    def test_create_intersecting_data(self):
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [
                    {"email": "shared@example.com"},
                    {"email": "shared@example.com", "swedish_ssn": "191212121212"},
                ],
            }
        )
        self.assertEqual(response.status_code, 400)

    def test_create_dryrun(self):
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"email": "dryrun@example.com"}],
                "dryrun": True,
            }
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(
            self.meeting.invites.filter(
                user_data={"email": "dryrun@example.com"}
            ).exists()
        )

    def test_create_invalid_role(self):
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["invalid_role"],
                "data": [{"email": "x@example.com"}],
            }
        )
        self.assertEqual(response.status_code, 400)

    def test_create_email_normalised(self):
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"email": "UPPER@Example.COM"}],
            }
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            self.meeting.invites.filter(
                user_data={"email": "upper@example.com"}
            ).exists()
        )

    def test_create_with_group_annotation(self):
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [
                    {"email": "a@example.com", "group": "committee"},
                    {"email": "b@example.com", "group": "committee"},
                ],
            }
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["invites"]["added"], 2)
        self.assertEqual(len(data["annotations"]), 1)
        self.assertEqual(data["annotations"][0]["name"], "group")
        self.assertEqual(data["annotations"][0]["added"], 2)

    def test_annotate_existing_invite(self):
        """Posting with a group annotation against an already-existing invite adds the annotation."""
        invite = self.meeting.invites.create(
            user_data={"email": "existing@example.com"}, roles=["pa"]
        )
        self.assertEqual(invite.group_annotations.count(), 0)

        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"email": "existing@example.com", "group": "committee"}],
            }
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["invites"]["added"], 0)
        self.assertEqual(data["invites"]["existed"], 1)
        self.assertEqual(data["annotations"][0]["name"], "group")
        self.assertEqual(data["annotations"][0]["added"], 1)
        invite.refresh_from_db()
        self.assertEqual(invite.group_annotations.count(), 1)

    def test_create_without_identity_field(self):
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"group": "committee"}],
            }
        )
        self.assertEqual(response.status_code, 400)

    def test_create_skips_empty_rows(self):
        # Empty dicts and whitespace-only rows (e.g. pasted from Excel) are skipped.
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [
                    {},
                    {"email": "real@example.com"},
                    {"email": "   ", "group": "\t"},
                    {},
                ],
            }
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["invites"]["added"], 1)
        self.assertTrue(
            self.meeting.invites.filter(
                user_data={"email": "real@example.com"}
            ).exists()
        )

    def test_create_invalid_annotation_key(self):
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"email": "x@example.com", "bogus": "val"}],
            }
        )
        self.assertEqual(response.status_code, 400)

    def test_create_grouprole_without_group_rejected(self):
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"email": "x@example.com", "grouprole": "chair"}],
            }
        )
        self.assertEqual(response.status_code, 400)

    def test_create_partial_match_updates_roles(self):
        """Existing invite with {email, ssn} can be updated by posting email only."""

        multi_invite = self.meeting.invites.create(
            user_data={"email": "multi@example.com", "swedish_ssn": "191212121212"},
            roles=["pv"],
        )
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"email": "multi@example.com"}],
            }
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["invites"]["changed"], 1)
        multi_invite.refresh_from_db()
        self.assertEqual(["pa"], multi_invite.roles)

    def test_create_problematic_partial_match(self):
        """Two DB invites sharing identity values in different combinations → 400."""
        self.meeting.invites.create(
            user_data={"email": "one@example.com", "swedish_ssn": "191212121212"},
            roles=["pa"],
        )
        self.meeting.invites.create(
            user_data={"email": "two@example.com", "swedish_ssn": "200001011234"},
            roles=["pa"],
        )
        # This row would partially match both invites (email→two, ssn→one's invite)
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"email": "two@example.com", "swedish_ssn": "191212121212"}],
            }
        )
        self.assertEqual(response.status_code, 400)

    def test_create_moderator_lockout(self):
        """Importing without moderator role when existing moderators have accepted invites → 400."""
        moderator = self.meeting.participants.get(username="moderator")
        moderator.userid = "moderator"
        moderator.save()
        self.meeting.invites.create(
            user_data={"email": "moderator@example.com"},
            roles=["mo", "pa"],
            used_by=moderator,
            state=InviteStateMachine.accepted.value,
        )
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"email": "moderator@example.com"}],
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("moderator", response.json()["non_field_errors"][0])

    def test_create_annotation_group_not_in_meeting(self):
        """Annotation with a group ID that doesn't exist in the meeting → 400."""
        response = self._post(
            {
                "meeting": self.meeting.pk,
                "roles": ["pa"],
                "data": [{"email": "x@example.com", "group": "nonexistent-group"}],
            }
        )
        self.assertEqual(response.status_code, 400)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class MeetingInviteViewSetAnnotationWsTests(APITestCase):
    """Verify that MeetingInviteChanged is published when annotations are added via REST."""

    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.moderator: User = cls.meeting.participants.get(username="moderator")
        cls.group = MeetingGroup.objects.create(meeting=cls.meeting, groupid="board")
        cls.invite = cls.meeting.invites.create(
            user_data={"email": "a@example.com"}, roles=["pa"]
        )

    def _post(self, data):
        self.client.force_login(self.moderator)
        return self.client.post(
            reverse("meeting-invites-list"),
            data,
            content_type="application/json",
        )

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_annotation_only_sends_invite_changed(self, mock_publish):
        """
        Adding an annotation to an existing invite (no new invite created, no invite saved)
        must still publish MeetingInviteChanged so the frontend learns about has_annotations.
        """
        with self.captureOnCommitCallbacks(execute=True):
            response = self._post(
                {
                    "meeting": self.meeting.pk,
                    "roles": ["pa"],
                    "data": [{"email": "a@example.com", "group": "board"}],
                }
            )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["invites"]["existed"], 1)
        self.assertEqual(data["annotations"][0]["added"], 1)

        changed_msgs = [
            call.args[0]
            for call in mock_publish.mock_calls
            if isinstance(call.args[0], MeetingInviteChanged)
        ]
        self.assertTrue(
            changed_msgs,
            "MeetingInviteChanged was not published after annotation was added",
        )
        self.assertEqual(self.invite.pk, changed_msgs[0].payload.pk)
        self.assertTrue(changed_msgs[0].payload.has_annotations)


class MeetingInviteViewSetClearAnnotationsTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.moderator: User = cls.meeting.participants.get(username="moderator")
        cls.group = MeetingGroup.objects.create(meeting=cls.meeting, groupid="board")
        cls.invite = cls.meeting.invites.create(
            user_data={"email": "a@example.com"}, roles=["pa"]
        )
        cls.invite_no_ann = cls.meeting.invites.create(
            user_data={"email": "b@example.com"}, roles=["pa"]
        )
        MeetingGroupAnnotation.objects.create(
            meeting_invite=cls.invite, meeting_group=cls.group
        )

    def _post(self, data):
        self.client.force_login(self.moderator)
        return self.client.post(
            "/api/meeting-invites/clear-annotations/",
            data,
            content_type="application/json",
        )

    def test_clear_removes_annotation(self):
        response = self._post({"meeting": self.meeting.pk, "invites": [self.invite.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cleared"], 1)
        self.assertEqual(self.invite.group_annotations.count(), 0)

    def test_clear_only_affects_specified_invites(self):
        other_invite = self.meeting.invites.create(
            user_data={"email": "c@example.com"}, roles=["pa"]
        )
        from voteit.invites.models import MeetingGroupAnnotation

        MeetingGroupAnnotation.objects.create(
            meeting_invite=other_invite, meeting_group=self.group
        )

        response = self._post({"meeting": self.meeting.pk, "invites": [self.invite.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cleared"], 1)
        self.assertEqual(other_invite.group_annotations.count(), 1)

    def test_clear_invite_without_annotation_returns_zero(self):
        response = self._post(
            {"meeting": self.meeting.pk, "invites": [self.invite_no_ann.pk]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cleared"], 0)

    def test_clear_rejects_invites_from_other_meeting(self):
        other_org = Organisation.objects.create()
        other_meeting = other_org.meetings.create(title="Other", state="ongoing")
        other_invite = other_meeting.invites.create(
            user_data={"email": "x@example.com"}, roles=["pa"]
        )
        response = self._post(
            {"meeting": self.meeting.pk, "invites": [other_invite.pk]}
        )
        self.assertEqual(response.status_code, 400)

    def test_clear_unauthenticated(self):
        response = self.client.post(
            "/api/meeting-invites/clear-annotations/",
            {"meeting": self.meeting.pk, "invites": [self.invite.pk]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_clear_sends_invite_changed_with_no_annotations(self, mock_publish):
        """Clearing annotations must publish MeetingInviteChanged with has_annotations=False."""
        self.client.force_login(self.moderator)
        response = self._post({"meeting": self.meeting.pk, "invites": [self.invite.pk]})
        self.assertEqual(response.status_code, 200)
        changed_msgs = [
            call.args[0]
            for call in mock_publish.mock_calls
            if isinstance(call.args[0], MeetingInviteChanged)
            and call.args[0].payload.pk == self.invite.pk
        ]
        self.assertTrue(
            changed_msgs,
            "MeetingInviteChanged was not published for the cleared invite",
        )
        self.assertFalse(changed_msgs[0].payload.has_annotations)


class InviteDataTypesViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="user")

    def test_basics(self):
        self.client.force_login(self.user)
        url = reverse("invite-data-types-list")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        email_data = [x for x in data if x["name"] == "email"][0]
        self.assertEqual(
            {
                "is_annotation": False,
                "is_user_data": True,
                "is_clearable": False,
                "is_runnable": True,
                "name": "email",
                "title": "Email",
            },
            email_data,
        )
        group_data = [x for x in data if x["name"] == "group"][0]
        self.assertEqual(
            {
                "is_annotation": True,
                "is_user_data": False,
                "is_clearable": True,
                "is_runnable": True,
                "name": "group",
                "title": "GroupID",
            },
            group_data,
        )

    def test_auth_required(self):
        url = reverse("invite-data-types-list")
        response = self.client.get(url)
        self.assertEqual(401, response.status_code)


class InviteStateMachineSchemaTests(APITestCase):
    def test_detail(self):
        response = self.client.get("/api/state-machines/InviteStateMachine/")
        self.assertEqual(200, response.status_code)
        self.assertIn("states", response.data)
        self.assertIn("events", response.data)
