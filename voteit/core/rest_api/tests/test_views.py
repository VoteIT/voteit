import io
import tempfile

from django.contrib.auth import get_user_model
from django.contrib.messages import success
from django.contrib.messages.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation
from voteit.organisation.roles import ROLE_ORG_MANAGER

User = get_user_model()


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


class UserViewSetTests(APITestCase):
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

    def _mk_fake_file(self, *, content_type: str = "image/webp", size: int = 1_00):
        # Memory saving method of creating file of requested size
        file_io = io.BytesIO()
        file_io.seek(size - 1)
        file_io.write(b"\0")
        file_io.seek(0)
        return SimpleUploadedFile("blob", file_io.read(), content_type=content_type)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_upload(self):
        self.client.force_login(self.participant)
        url = reverse("user-detail", kwargs={"pk": self.participant.pk})
        response = self.client.patch(
            url, data={"image": self._mk_fake_file()}, format="multipart"
        )
        self.assertContains(
            response, "http://testserver/media/profile_pics/blob", status_code=200
        )
        response = self.client.patch(
            url,
            data={"image": self._mk_fake_file(content_type="text/plain")},
            format="multipart",
        )
        self.assertContains(response, "Invalid content type", status_code=400)
        response = self.client.patch(
            url, data={"image": self._mk_fake_file(size=301_000)}, format="multipart"
        )
        self.assertContains(response, "File too big", status_code=400)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_clear_image(self):
        self.client.force_login(self.participant)
        url = reverse("user-detail", kwargs={"pk": self.participant.pk})
        self.participant.image = "/fake.file"
        self.participant.save()
        self.assertContains(
            self.client.get(url), "http://testserver/media/fake.file", status_code=200
        )
        response = self.client.patch(url, data={"image": ""}, format="multipart")
        self.assertContains(response, '"image":null', status_code=200)

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
                "image": None,
                "img_url": None,
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
                "image": None,
                "img_url": None,
                "last_name": "",
                "organisation": 1,
                "organisation_roles": [],
                "pk": 1,
                "userid": "moderator",
                "email": "moderator@voteit.se",
            },
            data,
        )

    def test_switch_authenticated_non_allowed_user(self):
        self.client.force_login(self.participant)
        url = reverse("user-switch", kwargs={"pk": 3})
        response = self.client.post(url)
        self.assertEqual(404, response.status_code)

    def test_logout(self):
        self.client.force_login(self.participant)
        url = reverse("user-logout")
        response = self.client.post(url)

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


class HealthTests(APITestCase):
    def test_healthcheck(self):
        url = reverse("health-list")
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
