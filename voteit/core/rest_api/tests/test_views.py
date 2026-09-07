from __future__ import annotations

import tempfile
from contextlib import ExitStack
from unittest.mock import patch

import statemachine.registry as sm_registry
from django.contrib.auth import get_user_model
from django.contrib.messages import success
from django.contrib.messages.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from social_django.models import UserSocialAuth
from statemachine import Event
from statemachine import State
from statemachine import StateChart

from voteit.core.sessions import end_tracked_sessions
from voteit.core.sessions import tracked_sessions
from voteit.core.testing import IsolatedCacheMixin
from voteit.core.statemachines import TransitionSignalMixin
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation
from voteit.organisation.roles import ROLE_ORG_MANAGER

User = get_user_model()

#: Patch targets live where the view imported them, not where they are defined.
VIEWS = "voteit.core.rest_api.views"


class UserSearchViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.org_manager = User.objects.get(username="org_manager")
        cls.meeting: Meeting = Meeting.objects.get(pk=1)

        # Other org
        cls.other_org: Organisation = Organisation.objects.create()
        cls.other_meeting: Meeting = Meeting.objects.create()
        cls.other_meeting_user = cls.other_org.users.create(
            username="other_meeting_user"
        )
        cls.other_meeting.add_roles(cls.other_meeting_user, ROLE_PARTICIPANT)
        cls.other_org_manager = cls.other_org.users.create(username="other_org_manager")
        cls.other_org.add_roles(cls.other_org_manager, ROLE_ORG_MANAGER)
        # And superuser
        cls.superuser = User.objects.create(
            username="super", is_superuser=True, organisation=cls.other_org
        )

    def test_list_superuser(self):
        url = reverse("users-list")
        self.client.force_login(self.superuser)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(3, len(data))

    def test_list_moderator_unspecified_context(self):
        url = reverse("users-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.json())

    def test_list_moderator_own_meeting(self):
        url = reverse("users-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url, data={"meeting": self.meeting.pk})
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(2, len(data))

    def test_list_moderator_other_meeting(self):
        url = reverse("users-list")
        self.client.force_login(self.moderator)
        response = self.client.get(url, data={"meeting": self.other_meeting.pk})
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(0, len(data))

    def test_list_org_manager_unspecified_context(self):
        url = reverse("users-list")
        self.client.force_login(self.org_manager)
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(3, len(data))
        self.assertEqual(
            {self.org_manager.pk, self.participant.pk, self.moderator.pk},
            {x["pk"] for x in data},
        )

    def test_list_anon(self):
        url = reverse("users-list")
        response = self.client.get(url)
        self.assertEqual(401, response.status_code)

    def test_participant_in_own_meeting(self):
        self.client.force_login(self.participant)
        url = reverse("users-list")
        response = self.client.get(url, data={"meeting": self.meeting.pk})
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(2, len(data))

    def test_update(self):
        self.client.force_login(self.superuser)
        url = reverse("users-detail", kwargs={"pk": self.superuser.pk})
        response = self.client.patch(url, data={"userid": "anewone"})
        self.assertEqual(405, response.status_code)

    def test_delete(self):
        self.client.force_login(self.superuser)
        url = reverse("users-detail", kwargs={"pk": self.superuser.pk})
        response = self.client.delete(url)
        self.assertEqual(405, response.status_code)

    def test_create(self):
        self.client.force_login(self.superuser)
        url = reverse("users-list")
        response = self.client.post(url, data={"userid": "anewone"})
        self.assertEqual(405, response.status_code)


class UserViewSetTests(IsolatedCacheMixin, APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.moderator.identity_id = "abc"
        cls.moderator.save()
        cls.participant = User.objects.get(username="participant")
        cls.participant.identity_id = "abc"
        cls.participant.save()
        cls.provider: OAuth2Provider = OAuth2Provider.objects.get(pk=1)
        cls.participant = User.objects.get(username="participant")

    def test_list(self):
        self.client.force_login(self.participant)
        url = reverse("user-list")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(2, data["pk"])

    def test_list_anon(self):
        url = reverse("user-list")
        response = self.client.get(url)
        self.assertEqual(401, response.status_code)

    def test_update(self):
        self.client.force_login(self.participant)
        url = reverse("user-detail", kwargs={"pk": self.participant.pk})
        response = self.client.put(url, data={"userid": "anewone"})
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(2, data["pk"])
        self.assertEqual("anewone", data["userid"])

    def test_update_other_user(self):
        self.client.force_login(self.participant)
        url = reverse("user-detail", kwargs={"pk": 3})
        response = self.client.put(url, data={"userid": "aneeewooone"})
        self.assertEqual(404, response.status_code)

    def test_update_owned_other_user(self):
        self.client.force_login(self.participant)
        url = reverse("user-detail", kwargs={"pk": 1})
        response = self.client.put(url, data={"userid": "aneeewooone"})
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertIn("userid", data)
        self.assertEqual("aneeewooone", data["userid"])

    def test_update_exists(self):
        self.client.force_login(self.participant)
        url = reverse("user-detail", kwargs={"pk": self.participant.pk})
        response = self.client.put(url, data={"userid": "moderator"})
        self.assertEqual(400, response.status_code)
        data = response.json()
        self.assertIn("userid", data)

    def test_update_anon(self):
        url = reverse("user-detail", kwargs={"pk": self.participant.pk})
        response = self.client.put(url, data={"userid": "moderator"})
        self.assertEqual(401, response.status_code)

    def test_update_bad_name(self):
        self.client.force_login(self.participant)
        url = reverse("user-detail", kwargs={"pk": self.participant.pk})
        response = self.client.put(url, data={"userid": "öäå"})
        self.assertEqual(400, response.status_code)
        data = response.json()
        self.assertIn("userid", data)

    def test_retrieve_alternate_users(self):
        self.client.force_login(self.participant)
        url = reverse("user-alternate")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(1, len(data))
        self.assertEqual(
            {
                "pk": 1,
                "userid": "moderator",
                "first_name": "Moderator",
                "last_name": "",
                "img_url": None,
                "image": None,
                "organisation": 1,
                "organisation_roles": [],
                "email": "moderator@voteit.se",
            },
            data[0],
        )

    def test_switch_anon(self):
        url = reverse("user-switch", kwargs={"pk": self.participant.pk})
        response = self.client.post(url)
        self.assertEqual(401, response.status_code)

    def test_switch_authenticated(self):
        self.client.force_login(self.participant)
        url = reverse("user-switch", kwargs={"pk": self.moderator.pk})
        response = self.client.post(url)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertEqual(
            {
                "first_name": "Moderator",
                "img_url": None,
                "image": None,
                "last_name": "",
                "organisation": 1,
                "organisation_roles": [],
                "pk": 1,
                "userid": "moderator",
                "email": "moderator@voteit.se",
            },
            data,
        )

    def test_switch_logs_in_new_user(self):
        self.client.force_login(self.participant)
        self.client.post(reverse("user-switch", kwargs={"pk": self.moderator.pk}))
        response = self.client.get(reverse("user-list"))
        self.assertEqual(200, response.status_code)
        self.assertEqual(self.moderator.pk, response.json()["pk"])

    def test_switch_authenticated_non_allowed_user(self):
        self.client.force_login(self.participant)
        url = reverse("user-switch", kwargs={"pk": 3})
        response = self.client.post(url)
        self.assertEqual(404, response.status_code)

    def test_switch_transfers_social_auths(self):
        self.participant.social_auth.create(uid="abc", provider="idproxy")
        self.client.force_login(self.participant)
        url = reverse("user-switch", kwargs={"pk": self.moderator.pk})
        response = self.client.post(url)
        self.assertEqual(200, response.status_code)
        social = UserSocialAuth.objects.get(provider="idproxy", uid="abc")
        self.assertEqual(self.moderator, social.user)

    def test_logout(self):
        self.client.force_login(self.participant)
        session_key = self.client.session.session_key
        url = reverse("user-logout")
        with patch(f"{VIEWS}.close_session_connections") as close:
            response = self.client.post(url)
        self.assertEqual(200, response.status_code)
        self.assertNotIn("_auth_user_id", self.client.session)
        close.assert_called_once()
        self.assertEqual(session_key, close.call_args.args[0])

    def test_logout_closes_only_that_sessions_sockets(self):
        """The socket scope's user is resolved once, at handshake, so nothing
        else would ever tell the other tab it had been logged out."""
        self.client.force_login(self.participant)
        session_key = self.client.session.session_key
        with ExitStack() as stack:
            close_session = stack.enter_context(
                patch(f"{VIEWS}.close_session_connections")
            )
            close_user = stack.enter_context(patch(f"{VIEWS}.close_user_connections"))
            self.client.post(reverse("user-logout"))
        close_session.assert_called_once()
        self.assertEqual(session_key, close_session.call_args.args[0])
        close_user.assert_not_called()

    def test_logout_everywhere_closes_every_socket_and_flushes(self):
        self.client.force_login(self.participant)
        with ExitStack() as stack:
            close_session = stack.enter_context(
                patch(f"{VIEWS}.close_session_connections")
            )
            close_user = stack.enter_context(patch(f"{VIEWS}.close_user_connections"))
            response = self.client.post(
                reverse("user-logout"), {"everywhere": True}, format="json"
            )
        self.assertEqual(200, response.status_code)
        close_session.assert_not_called()
        self.assertEqual(self.participant.pk, close_user.call_args.args[0])
        # Without this the sockets close but the sessions behind them live on.
        self.assertIs(True, close_user.call_args.kwargs["flush_session"])

    def test_logout_everywhere_ends_the_other_session(self):
        other = self.client_class()
        other.force_login(self.participant)
        self.client.force_login(self.participant)

        with patch(f"{VIEWS}.close_user_connections"):
            self.client.post(
                reverse("user-logout"), {"everywhere": True}, format="json"
            )

        self.assertNotIn("_auth_user_id", other.session)

    def test_an_ordinary_logout_leaves_the_other_session_alone(self):
        other = self.client_class()
        other.force_login(self.participant)
        self.client.force_login(self.participant)

        with patch(f"{VIEWS}.close_session_connections"):
            self.client.post(reverse("user-logout"))

        self.assertIn("_auth_user_id", other.session)

    def test_switching_user_does_not_leave_a_key_that_could_kill_the_new_session(self):
        """switch() re-points one session at another user, so the first user
        keeps a tracked key for a session that is now somebody else's. It must
        not be able to end it. Django saves us here -- login() cycles the key
        when the user changes -- but the consequence if that ever stopped being
        true is one user logging another out, so it is pinned."""
        self.client.force_login(self.participant)
        stale_key = self.client.session.session_key
        self.client.post(reverse("user-switch", kwargs={"pk": self.moderator.pk}))
        self.assertNotEqual(stale_key, self.client.session.session_key)
        self.assertEqual(self.moderator.pk, int(self.client.session["_auth_user_id"]))

        end_tracked_sessions(self.participant.pk)

        self.assertIn("_auth_user_id", self.client.session)

    def test_an_ordinary_logout_stops_tracking_its_own_session(self):
        """Otherwise every logout leaves a dead key behind for the next
        "everywhere" to walk over."""
        self.client.force_login(self.participant)
        session_key = self.client.session.session_key
        self.assertIn(session_key, tracked_sessions(self.participant.pk))

        with patch(f"{VIEWS}.close_session_connections"):
            self.client.post(reverse("user-logout"))

        self.assertNotIn(session_key, tracked_sessions(self.participant.pk))

    def test_email_choices(self):
        self.client.force_login(self.participant)
        self.participant.social_auth.create(
            uid="abc",
            provider="idproxy",
            extra_data={
                "user_data": {"email": ["hello@betahaus.net", "world@betahaus.net"]}
            },
        )
        url = reverse("user-email-choices")
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(200, response.status_code, data)
        self.assertEqual({"emails": ["hello@betahaus.net", "world@betahaus.net"]}, data)

    def test_messages(self):
        request = RequestFactory().request()
        request.session = self.client.session
        request._messages = default_storage(request)
        success(request, "Hello there!")
        request._messages.update(None)
        request.session.save()
        url = reverse("user-messages")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            [
                {
                    "level": 25,
                    "level_tag": "success",
                    "message": "Hello there!",
                    "tags": "success",
                }
            ],
            response.json(),
        )
        # Message consumed
        response = self.client.get(url)
        self.assertEqual(
            [],
            response.json(),
        )


# Minimal structurally valid images (same constants as in test_validators.py)
_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
_WEBP = b"RIFF\x04\x00\x00\x00WEBP"
_GIF = (
    b"GIF89a\x01\x00\x01\x00\x00\xff\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x00;"
)


class UserImageAPITests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.participant = User.objects.get(username="participant")
        cls.participant.identity_id = "img-test"
        cls.participant.save()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._override = override_settings(
            MEDIA_ROOT=self._tmp.name,
            MEDIA_URL="/media/",
        )
        self._override.enable()

    def tearDown(self):
        self._override.disable()
        self._tmp.cleanup()

    def _url(self):
        return reverse("user-detail", kwargs={"pk": self.participant.pk})

    def _patch(self, content, name="photo.jpg", content_type="image/jpeg"):
        return self.client.patch(
            self._url(),
            data={
                "image": SimpleUploadedFile(name, content, content_type=content_type)
            },
            format="multipart",
        )

    # — Successful uploads —

    def test_upload_jpeg(self):
        self.client.force_login(self.participant)
        response = self._patch(_JPEG)
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertIsNotNone(data["image"])
        self.assertIn(f"org_{self.participant.organisation_id}/images/", data["image"])
        self.assertTrue(data["image"].endswith(".jpg"))

    def test_upload_png(self):
        self.client.force_login(self.participant)
        response = self._patch(_PNG, "photo.png", "image/png")
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json()["image"].endswith(".png"))

    def test_upload_webp(self):
        self.client.force_login(self.participant)
        response = self._patch(_WEBP, "photo.webp", "image/webp")
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json()["image"].endswith(".webp"))

    def test_file_written_to_disk(self):
        self.client.force_login(self.participant)
        self.assertEqual(200, self._patch(_JPEG).status_code)
        self.participant.refresh_from_db()
        self.assertTrue(self.participant.image)
        self.assertTrue(
            self.participant.image.storage.exists(self.participant.image.name)
        )

    def test_replace_image_returns_new_url(self):
        self.client.force_login(self.participant)
        r1 = self._patch(_JPEG, "first.jpg")
        self.assertEqual(200, r1.status_code)
        url1 = r1.json()["image"]

        r2 = self._patch(_PNG, "second.png", "image/png")
        self.assertEqual(200, r2.status_code)
        url2 = r2.json()["image"]

        self.assertNotEqual(url1, url2)
        self.assertTrue(url2.endswith(".png"))

    # — Rejected uploads —

    def test_invalid_format_rejected(self):
        self.client.force_login(self.participant)
        response = self._patch(_GIF, "photo.gif", "image/gif")
        self.assertEqual(400, response.status_code)
        self.assertIn("image", response.json())

    def test_malicious_php_content_rejected(self):
        self.client.force_login(self.participant)
        response = self._patch(b"<?php system($_GET['cmd']); ?>", "photo.jpg")
        self.assertEqual(400, response.status_code)

    def test_oversized_file_rejected(self):
        # Default max_size is 300kb, pad JPEG bytes well beyond that
        self.client.force_login(self.participant)
        response = self._patch(_JPEG + b"\x00" * 350_000)
        self.assertEqual(400, response.status_code)
        self.assertIn("image", response.json())

    # — Auth —

    def test_anon_cannot_upload(self):
        response = self._patch(_JPEG)
        self.assertEqual(401, response.status_code)


class HealthTests(APITestCase):
    def test_healthcheck(self):
        url = reverse("health-list")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)


class StateMachinesViewTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with patch.object(sm_registry, "_REGISTRY", {}):

            class DummyWorkflow(StateChart, TransitionSignalMixin):
                draft = State(value="draft", initial=True)
                published = State(value="published", final=True)

                publish = Event(draft.to(published))

            cls.DummyWorkflow = DummyWorkflow

    def _registry_patch(self):
        qn = f"{self.DummyWorkflow.__module__}.{self.DummyWorkflow.__qualname__}"
        return (
            patch.object(sm_registry, "_REGISTRY", {qn: self.DummyWorkflow}),
            patch.object(sm_registry, "_initialized", True),
        )

    def _get_list(self):
        key = self.DummyWorkflow.__name__
        with ExitStack() as stack:
            for p in self._registry_patch():
                stack.enter_context(p)
            return self.client.get("/api/state-machines/"), key

    def _get_detail(self, name=None):
        key = name or self.DummyWorkflow.__name__
        with ExitStack() as stack:
            for p in self._registry_patch():
                stack.enter_context(p)
            return self.client.get(f"/api/state-machines/{key}/"), key

    def test_list_returns_200(self):
        response, _ = self._get_list()
        self.assertEqual(response.status_code, 200)

    def test_list_includes_workflow(self):
        response, key = self._get_list()
        self.assertIn(key, response.data)

    def test_states_are_dict_keyed_by_id(self):
        response, key = self._get_list()
        states = response.data[key]["states"]
        self.assertIn("draft", states)
        self.assertIn("published", states)

    def test_state_has_name_and_flags(self):
        response, key = self._get_list()
        states = response.data[key]["states"]
        self.assertTrue(states["draft"]["initial"])
        self.assertTrue(states["published"]["final"])
        self.assertNotIn("initial", states["published"])

    def test_events_are_dict_keyed_by_id(self):
        response, key = self._get_list()
        events = response.data[key]["events"]
        self.assertIn("publish", events)

    def test_event_transition_from_to(self):
        response, key = self._get_list()
        transition = response.data[key]["events"]["publish"]["transitions"][0]
        self.assertEqual(transition["from"], "draft")
        self.assertEqual(transition["to"], "published")

    def test_transition_includes_validators_and_cond(self):
        response, key = self._get_list()
        transition = response.data[key]["events"]["publish"]["transitions"][0]
        self.assertIn("validators", transition)
        self.assertIn("cond", transition)

    def test_detail_returns_200(self):
        response, _ = self._get_detail()
        self.assertEqual(response.status_code, 200)

    def test_detail_returns_single_machine(self):
        response, _ = self._get_detail()
        self.assertIn("states", response.data)
        self.assertIn("events", response.data)

    def test_detail_unknown_name_returns_404(self):
        response, _ = self._get_detail(name="NoSuchMachine")
        self.assertEqual(response.status_code, 404)

    def test_not_allowed_cond_excludes_transition(self):
        from voteit.core import NOT_ALLOWED_SM_GUARD

        with patch.object(sm_registry, "_REGISTRY", {}):

            class WorkflowWithRestricted(StateChart, TransitionSignalMixin):
                draft = State(value="draft", initial=True)
                published = State(value="published")
                archived = State(value="archived", final=True)

                publish = Event(draft.to(published))
                archive = Event(
                    draft.to(archived, cond=[NOT_ALLOWED_SM_GUARD])
                    | published.to(archived, cond=[NOT_ALLOWED_SM_GUARD])
                )

                def not_allowed(self, **kw):
                    return False

            qn = f"{WorkflowWithRestricted.__module__}.{WorkflowWithRestricted.__qualname__}"
            patches = (
                patch.object(sm_registry, "_REGISTRY", {qn: WorkflowWithRestricted}),
                patch.object(sm_registry, "_initialized", True),
            )
            key = WorkflowWithRestricted.__name__
            with ExitStack() as stack:
                for p in patches:
                    stack.enter_context(p)
                response = self.client.get(f"/api/state-machines/{key}/")

        events = response.data["events"]
        self.assertIn("publish", events)
        self.assertNotIn("archive", events)

    def test_not_allowed_cond_on_some_transitions_keeps_event(self):
        from voteit.core import NOT_ALLOWED_SM_GUARD

        with patch.object(sm_registry, "_REGISTRY", {}):

            class WorkflowPartialRestricted(StateChart, TransitionSignalMixin):
                draft = State(value="draft", initial=True)
                review = State(value="review")
                archived = State(value="archived", final=True)

                submit = Event(
                    draft.to(review) | review.to(archived, cond=[NOT_ALLOWED_SM_GUARD])
                )

                def not_allowed(self, **kw):
                    return False

            qn = f"{WorkflowPartialRestricted.__module__}.{WorkflowPartialRestricted.__qualname__}"
            patches = (
                patch.object(sm_registry, "_REGISTRY", {qn: WorkflowPartialRestricted}),
                patch.object(sm_registry, "_initialized", True),
            )
            key = WorkflowPartialRestricted.__name__
            with ExitStack() as stack:
                for p in patches:
                    stack.enter_context(p)
                response = self.client.get(f"/api/state-machines/{key}/")

        events = response.data["events"]
        self.assertIn("submit", events)
        transitions = events["submit"]["transitions"]
        self.assertEqual(1, len(transitions))
        self.assertEqual("draft", transitions[0]["from"])
        self.assertEqual("review", transitions[0]["to"])
