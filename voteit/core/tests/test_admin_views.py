from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now

from voteit.core.admin import OnlineFilter
from voteit.messaging.models import Connection
from voteit.organisation.models import Organisation


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


class OnlineFilterTests(TestCase):
    """The user changelist's Online / Disconnected / Within-30-days filter.

    Connection has no FK to User, so this filter goes through a subquery. It
    had no coverage at all before, and it silently duplicated the "how long
    counts as online" window that voteit.messaging owns.
    """

    changelist_url = reverse("admin:core_user_changelist")
    stale_after = 15 * 60

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.org = Organisation.objects.create(title="Org", host="org.example.com")
        cls.online = User.objects.create(username="online", organisation=cls.org)
        cls.silent = User.objects.create(username="silent", organisation=cls.org)
        cls.ancient = User.objects.create(username="ancient", organisation=cls.org)
        cls.never = User.objects.create(username="never", organisation=cls.org)
        cls.admin_user = User.objects.create_superuser(username="filter-admin")

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)

    def _connect(self, user, *, ago, code=None):
        Connection.objects.create(
            user_id=user.pk,
            channel_name=f"{user.username}-{ago}",
            connected_at=now() - timedelta(seconds=ago + 60),
            last_action=now() - timedelta(seconds=ago),
            code=code,
        )

    def _usernames(self, value):
        response = self.client.get(self.changelist_url, {"online": value})
        self.assertEqual(200, response.status_code)
        return {obj.username for obj in response.context["cl"].result_list}

    def _populate(self):
        self._connect(self.online, ago=5)
        self._connect(self.silent, ago=self.stale_after + 60)
        self._connect(self.ancient, ago=60 * 60 * 24 * 40)

    @override_settings(VOTEIT_CONNECTION_STALE_AFTER=stale_after)
    def test_online(self):
        self._populate()
        self.assertEqual({"online"}, self._usernames(OnlineFilter.ONLINE))

    @override_settings(VOTEIT_CONNECTION_STALE_AFTER=stale_after)
    def test_disconnected_covers_users_with_no_connection_at_all(self):
        self._populate()
        self.assertEqual(
            {"silent", "ancient", "never", "filter-admin"},
            self._usernames(OnlineFilter.DISCONNECTED),
        )

    @override_settings(VOTEIT_CONNECTION_STALE_AFTER=stale_after)
    def test_a_closed_socket_is_not_online(self):
        self._connect(self.online, ago=5, code=1000)
        self.assertEqual(set(), self._usernames(OnlineFilter.ONLINE))

    @override_settings(VOTEIT_CONNECTION_STALE_AFTER=stale_after)
    def test_within_last_month(self):
        self._populate()
        self.assertEqual(
            {"online", "silent"}, self._usernames(OnlineFilter.WITHIN_LAST_MONTH)
        )

    @override_settings(VOTEIT_CONNECTION_STALE_AFTER=2 * 60 * 60)
    def test_window_follows_the_setting(self):
        # Silent for well over the default 15 minutes, but inside a 2h window.
        self._populate()
        self.assertEqual({"online", "silent"}, self._usernames(OnlineFilter.ONLINE))
