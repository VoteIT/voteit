from django.contrib.auth import get_user_model
from django.test import TestCase
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.messages.app_state import AppState


class TestAppState(TestCase):
    def setUp(self):
        class TestOutgoing(BaseOutgoingMessage):
            name = 'test'
        self.test_outgoing = TestOutgoing()

    def test_append(self):
        from voteit.messaging.envelopes import BaseEnvelope
        app_state = AppState()
        with self.assertRaises(ValueError):
            app_state.append('string object')

        app_state.append(self.test_outgoing)
        self.assertEqual(len(app_state), 1)
        self.assertIsInstance(app_state[0], BaseEnvelope)
        self.assertEqual(app_state[0].t, self.test_outgoing.name)

    def test_append_from(self):
        from rest_framework.serializers import ModelSerializer
        User = get_user_model()

        class UserSerializer(ModelSerializer):
            class Meta:
                model = User
                fields = 'pk',

        app_state = AppState()
        app_state.append_from(User(first_name='test'), UserSerializer, self.test_outgoing.__class__)
        self.assertEqual(len(app_state), 1)
