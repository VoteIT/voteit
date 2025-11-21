from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from envelope.testing import testing_channel_layers_setting
from social_django.models import UserSocialAuth

from voteit.organisation.jobs import cleanup_extra_data_for_older_users
from voteit.organisation.models import Organisation


User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class JobsTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.get(pk=1)
        cls.usa = UserSocialAuth.objects.get(pk=1)
        cls.usa2 = UserSocialAuth.objects.create(
            user_id=1, extra_data={"email": "mine@betahaus.net"}, uid="abcdefg"
        )

    def test_cleanup_extra_data(self):
        self.assertEqual({"hello": "world"}, self.usa.extra_data)
        cleanup_extra_data_for_older_users()
        self.usa.refresh_from_db()
        self.usa2.refresh_from_db()
        self.assertEqual({}, self.usa.extra_data)
        self.assertEqual({"email": "mine@betahaus.net"}, self.usa2.extra_data)
