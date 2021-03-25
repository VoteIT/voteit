from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase


class OrganisationViewSetTests(APITestCase):
    def setUp(self):
        from voteit.organisation.models import Organisation

        self.org: Organisation = Organisation.objects.create(
            title="Test org",
        )
        self.manager = self.org.users.create(username="manager")
        self.user = self.org.users.create(username="user")

    # def test_create(self):
    #     url = reverse("organisation-list")
    #     data = {
    #         "title": "Item no 1",
    #     }
    #     for user, status in (
    #         (None, 401),
    #         (self.user, 403),
    #         (self.manager, 201),
    #     ):
    #         if user:
    #             self.client.force_login(user)
    #         response = self.client.post(url, data)
    #         self.assertEqual(
    #             response.status_code,
    #             status,
    #             f"{user} action returned wrong response code",
    #         )

    def test_get(self):
        url = f"/api/organisations/{self.org.pk}/"
        self.client.force_login(self.manager)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(self.org.pk, data["pk"])
