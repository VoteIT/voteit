from django.contrib.auth import get_user_model
from django.test import TestCase
from voteit.messaging.errors import UnauthorizedError, ValidationErrorMsg

User = get_user_model()


class _PresenceFixture:

    def fixture(self):
        from voteit.presence.models import PresenceSystem
        from voteit.presence.models import PresenceCheck
        from voteit.meeting.models import Meeting
        self.user = User.objects.create(username="creeper")
        self.meeting = Meeting.objects.create()
        self.meeting.add_roles(self.user, "participant")
        self.system = PresenceSystem.objects.create(meeting=self.meeting)
        self.check = PresenceCheck.objects.create(presence_system=self.system)


class AddPresenceTests(TestCase, _PresenceFixture):

    def setUp(self):
        self.fixture()

    @property
    def _cut(self):
        from voteit.presence.messages import AddPresence
        return AddPresence

    def _mk_one(self):
        return self._cut({"user_pk": self.user.pk}, pk=self.check.pk)

    def test_add(self):
        self.assertFalse(self.check.present_users.count())
        msg = self._mk_one()
        msg.run_job()
        self.assertTrue(self.check.present_users.count())

    def test_add_closed_check(self):
        self.check.close()
        self.check.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_add_not_participant(self):
        self.meeting.remove_roles(self.user, "participant")
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)


class RemovePresenceTests(TestCase, _PresenceFixture):

    def setUp(self):
        from voteit.presence.models import Presence
        self.fixture()
        self.presence = Presence.objects.create(user=self.user, presence_check=self.check)

    @property
    def _cut(self):
        from voteit.presence.messages import DeletePresence
        return DeletePresence

    def _mk_one(self):
        return self._cut({"user_pk": self.user.pk}, pk=self.presence.pk)

    def test_delete(self):
        self.assertTrue(self.check.present_users.count())
        msg = self._mk_one()
        msg.run_job()
        self.assertFalse(self.check.present_users.count())

    def test_delete_closed_check(self):
        self.check.close()
        self.check.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_delete_other_user(self):
        other = User.objects.create(username="another")
        self.meeting.add_roles(other, "participant")
        msg = self._mk_one()
        msg.mm.user_pk = other.pk
        self.assertRaises(UnauthorizedError, msg.run_job)


class AddUserPresenceTests(TestCase, _PresenceFixture):

    def setUp(self):
        self.fixture()
        self.moderator = User.objects.create(username="moderator")
        self.meeting.add_roles(self.moderator, "moderator")

    @property
    def _cut(self):
        from voteit.presence.messages import AddUserPresence
        return AddUserPresence

    def _mk_one(self):
        return self._cut({"user_pk": self.moderator.pk}, pk=self.check.pk, userid=self.user.pk)

    def test_add(self):
        self.assertFalse(self.check.present_users.count())
        msg = self._mk_one()
        msg.run_job()
        self.assertTrue(self.check.present_users.count())

    def test_add_closed_check(self):
        self.check.close()
        self.check.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_add_not_participant(self):
        self.meeting.remove_roles(self.user, "participant")
        msg = self._mk_one()
        self.assertRaises(ValidationErrorMsg, msg.run_job)

    def test_add_regular_user(self):
        self.meeting.remove_roles(self.moderator, "moderator")
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_add_non_existing_userid(self):
        msg = self._mk_one()
        msg.data.userid = -1
        self.assertRaises(ValidationErrorMsg, msg.run_job)


class RemoveUserPresenceTests(TestCase, _PresenceFixture):

    def setUp(self):
        from voteit.presence.models import Presence
        self.fixture()
        self.presence = Presence.objects.create(user=self.user, presence_check=self.check)
        self.moderator = User.objects.create(username="moderator")
        self.meeting.add_roles(self.moderator, "moderator")

    @property
    def _cut(self):
        from voteit.presence.messages import DeleteUserPresence
        return DeleteUserPresence

    def _mk_one(self):
        return self._cut({"user_pk": self.moderator.pk}, pk=self.presence.pk, userid=self.user.pk)

    def test_delete(self):
        self.assertTrue(self.check.present_users.count())
        msg = self._mk_one()
        msg.run_job()
        self.assertFalse(self.check.present_users.count())

    def test_delete_closed_check(self):
        self.check.close()
        self.check.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_delete_regular_user(self):
        self.meeting.remove_roles(self.moderator, "moderator")
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)


# class RolesIntegrationTests(TestCase):
#     def setUp(self):
#         self.user_a = User.objects.create(username="abel")
#         self.user_b = User.objects.create(username="bret")
#         self.meeting = Meeting.objects.create()
#         self.meeting.add_roles(self.user_a, "moderator")
#         self.meeting.add_roles(self.user_b, "moderator")
#
#     async def test_roles_removed_kicks_user_from_protected_channel(self):
#         from voteit.messaging.consumers import WebsocketDemuxConsumer
#         from voteit.meeting.channels import ModeratorChannel
#         from voteit.messaging.messages.channels import ChannelSubscription
#         from voteit.messaging.messages.roles import RemoveMeetingRoles
#
#         fakeredis_conn = FakeRedis()
#
#         queue = get_queue(TESTING_QUEUE, autocommit=True, connection=fakeredis_conn)
#
#         worker = SimpleWorker(
#             queues=[queue],
#             connection=fakeredis_conn,
#             disable_default_exception_handler=True,
#             log_job_description=False,
#         )
#
#         consumer_a = WebsocketDemuxConsumer()
#         consumer_a.refresh_user = mock.AsyncMock(return_value=self.user_a)
#         consumer_a.get_queue = mock.MagicMock(return_value=queue)
#
#         consumer_b = WebsocketDemuxConsumer()
#         consumer_b.refresh_user = mock.AsyncMock(return_value=self.user_b)
#         consumer_b.get_queue = mock.MagicMock(return_value=queue)
#
#         # Subscribe both users to the moderator channel
#         mod_channel = ModeratorChannel.from_instance(self.meeting)
#         subscription = ChannelSubscription(
#             pk=self.meeting.pk,
#             channel_type=mod_channel.name,
#             channel_name=mod_channel.channel_name,
#         )
#         consumer_a.mark_subscribed(subscription)
#         consumer_b.mark_subscribed(subscription)
#
#         # And connect
#         communicator_a = WebsocketCommunicator(consumer_a, "/testws")
#         connected_a, subprotocol = await communicator_a.connect()
#         assert connected_a
#
#         communicator_b = WebsocketCommunicator(consumer_b, "/testws")
#         connected_b, subprotocol = await communicator_b.connect()
#         assert connected_b
#
#         try:
#             # User A sends this message
#             msg = RemoveMeetingRoles(
#                 mm={"user_pk": self.user_a.pk},
#                 userids=[self.user_a.pk, self.user_b.pk],
#                 roles=["moderator"],
#                 pk=self.meeting.pk,
#             )
#             await consumer_a.handle_message(msg)
#             completed = await sync_to_async(worker.work)(burst=True)
#             self.failUnless(completed)
#             # Consumers must receive the messages to act
#             await communicator_a.receive_from()
#             await communicator_b.receive_from()
#
#             self.assertFalse(consumer_a.protected_subscriptions)
#             self.assertFalse(consumer_b.protected_subscriptions)
#         finally:
#             await communicator_a.disconnect()
#             await communicator_b.disconnect()
