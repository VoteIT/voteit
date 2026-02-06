from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse


def get_all_admin_urls(admin_user):
    site = admin.site
    request = RequestFactory().get("/")
    request.user = admin_user
    for model, model_admin in site._registry.items():
        if model.__module__.startswith("voteit."):
            app_label = model._meta.app_label
            model_name = model._meta.model_name

            # changelist
            yield reverse(f"admin:{app_label}_{model_name}_changelist")

            # add
            if model_admin.has_add_permission(request):
                yield reverse(f"admin:{app_label}_{model_name}_add")


class AdminViewsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Skapa en superuser för att kunna logga in
        User = get_user_model()
        cls.admin_user = User.objects.create_superuser(
            username="admin",
        )

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)

    def test_admin_views(self):
        for url in get_all_admin_urls(self.admin_user):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(200, response.status_code)
