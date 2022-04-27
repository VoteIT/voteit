from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

User = get_user_model()


class UserSearchViewSetTests(APITestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.organisation.models import Organisation

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
        cls.other_meeting.add_roles(cls.other_meeting_user, "participant")
        cls.other_org_manager = cls.other_org.users.create(username="other_org_manager")
        cls.other_org.add_roles(cls.other_org_manager, "org_manager")
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
            set([x["pk"] for x in data]),
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
        self.assertEqual(0, len(data))

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

    def setUp(self):
        self.participant = User.objects.get(username="participant")

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
                "state": "incomplete",
                "userid": "moderator",
                "full_name": "Moderator",
                "first_name": "Moderator",
                "last_name": "",
                "img_url": None,
                "organisation": 1,
                "organisation_roles": [],
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
                "full_name": "Moderator",
                "img_url": None,
                "last_name": "",
                "organisation": 1,
                "organisation_roles": [],
                "pk": 1,
                "state": "incomplete",
                "userid": "moderator",
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
        # FIXME: Check destroyed session?
