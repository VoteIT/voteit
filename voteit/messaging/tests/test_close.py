"""Closing sockets from the server.

The handler's own contract is in test_consumer.py; this is about the senders --
which sockets each one reaches, and which it leaves alone. That distinction is
the whole point of the session group: an ordinary logout must not disconnect
the same user's phone, whose session is still perfectly valid.
"""

from __future__ import annotations

from unittest.mock import patch

from channels.db import database_sync_to_async
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import AsyncClient
from django.test import TestCase
from django.urls import reverse
from io import StringIO

from voteit.core.messages.notice import Notice
from voteit.messaging.close import close_all_connections
from voteit.messaging.close import close_session_connections
from voteit.messaging.close import close_user_connections
from voteit.messaging.models import GOING_AWAY
from voteit.messaging.models import LOGGED_OUT
from voteit.messaging.models import LOGGED_OUT_EVERYWHERE
from voteit.messaging.models import NORMAL_CLOSURE
from voteit.messaging.models import Connection
from voteit.messaging.testing import ChannelMessageCatcher
from voteit.messaging.testing import MessageCatcher
from voteit.messaging.testing import ws_test_settings
from voteit.organisation.channels import OrganisationChannel
from voteit.organisation.models import Organisation

from .test_consumer import ConsumerTestCase


class LiveSocketTests(ConsumerTestCase):
    """Against real sockets, because the thing being tested is which group a
    consumer joined -- which nothing but a live handshake decides."""

    async def _connect_as(self, user, client=None):
        """Connect a socket for `user`, on `client`'s session.

        Pass an existing client for a second tab on the same session; leave it
        out for a separate one, the way another browser or a phone would be.
        Returns the communicator and its client.
        """
        client = client or AsyncClient()
        await client.aforce_login(user)
        headers = list(self.ws_headers)
        headers.append((b"cookie", client.cookies.output(header="", sep="; ").encode()))
        communicator = self.create_communicator(headers=headers)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        # These users have no organisation, so s.versions is all that arrives.
        await self._receive_one(communicator)
        return communicator, client

    @staticmethod
    def _session_key(client):
        return client.cookies[settings.SESSION_COOKIE_NAME].value

    async def _assert_closed(self, communicator, code=NORMAL_CLOSURE, notice=None):
        """Drain up to the close, checking the code and any s.msg before it.

        `notice` is the (type, message) pair the socket should have been shown
        first; the ordering matters, since a notice that arrived after the
        close would never be seen.
        """
        messages = await communicator.receive_all_messages(
            stop_action="s.closing", timeout=2
        )
        actions = [m.action for m in messages]
        closing = next(m for m in messages if m.action == "s.closing")
        self.assertEqual(code, closing.payload.code)
        if notice is None:
            self.assertNotIn("s.msg", actions)
        else:
            self.assertLess(actions.index("s.msg"), actions.index("s.closing"))
            msg = next(m for m in messages if m.action == "s.msg")
            self.assertEqual(notice, (msg.payload.type, msg.payload.message))
        return closing

    async def test_logout_closes_every_tab_on_that_session(self):
        first, client = await self._connect_as(self.moderator)
        second, _ = await self._connect_as(self.moderator, client)

        await database_sync_to_async(close_session_connections)(
            self._session_key(client),
            notice=Notice(
                payload={"type": "info", "message": "You have been logged out."}
            ),
        )

        for communicator in (first, second):
            await self._assert_closed(
                communicator, notice=("info", "You have been logged out.")
            )

    async def test_logout_leaves_the_same_users_other_session_alone(self):
        """The reported bug's mirror image: fixing the second tab must not
        disconnect the phone, which is still logged in."""
        _, client = await self._connect_as(self.moderator)
        elsewhere, _ = await self._connect_as(self.moderator)

        await database_sync_to_async(close_session_connections)(
            self._session_key(client)
        )

        self.assertTrue(await elsewhere.receive_nothing(timeout=0.5))
        await elsewhere.disconnect()

    async def test_logout_leaves_another_user_alone(self):
        _, client = await self._connect_as(self.moderator)
        other, _ = await self._connect_as(self.participant)

        await database_sync_to_async(close_session_connections)(
            self._session_key(client)
        )

        self.assertTrue(await other.receive_nothing(timeout=0.5))
        await other.disconnect()

    async def test_logout_everywhere_reaches_every_session(self):
        here, _ = await self._connect_as(self.moderator)
        elsewhere, _ = await self._connect_as(self.moderator)
        other_user, _ = await self._connect_as(self.participant)

        await database_sync_to_async(close_user_connections)(
            self.moderator.pk,
            flush_session=True,
            notice=Notice(
                payload={"type": "info", "message": "Logged out everywhere."}
            ),
        )

        for communicator in (here, elsewhere):
            await self._assert_closed(
                communicator, notice=("info", "Logged out everywhere.")
            )
        self.assertTrue(await other_user.receive_nothing(timeout=0.5))
        await other_user.disconnect()

    async def test_the_logout_endpoint_closes_that_sessions_socket(self):
        """End to end, nothing patched: the reported bug, from the REST call
        the SPA actually makes down to the frame the other tab receives."""
        first, client = await self._connect_as(self.moderator)
        second, _ = await self._connect_as(self.moderator, client)
        elsewhere, _ = await self._connect_as(self.moderator)

        response = await client.post(reverse("user-logout"))

        self.assertEqual(200, response.status_code)
        for communicator in (first, second):
            # 4000 and no s.msg: the code is the whole message, and the SPA is
            # what words it.
            await self._assert_closed(communicator, code=LOGGED_OUT)
        self.assertTrue(await elsewhere.receive_nothing(timeout=0.5))
        await elsewhere.disconnect()

    async def test_the_logout_endpoint_with_everywhere_reaches_every_session(self):
        here, client = await self._connect_as(self.moderator)
        elsewhere, _ = await self._connect_as(self.moderator)
        other_user, _ = await self._connect_as(self.participant)

        response = await client.post(
            reverse("user-logout"),
            data={"everywhere": True},
            content_type="application/json",
        )

        self.assertEqual(200, response.status_code)
        for communicator in (here, elsewhere):
            # A separate code from the 4000 above, because the SPA words "you
            # were logged out here" and "on every device" differently.
            await self._assert_closed(communicator, code=LOGGED_OUT_EVERYWHERE)
        self.assertTrue(await other_user.receive_nothing(timeout=0.5))
        await other_user.disconnect()

    async def test_the_connection_row_is_closed_too(self):
        """Otherwise every deliberate close looks like a socket that vanished:
        the row stays open until the stale-connection job reaps it."""
        communicator, client = await self._connect_as(self.moderator)

        await database_sync_to_async(close_session_connections)(
            self._session_key(client)
        )
        await self._assert_closed(communicator)

        rows = await database_sync_to_async(
            lambda: list(Connection.objects.values_list("code", flat=True))
        )()
        self.assertEqual([NORMAL_CLOSURE], rows)

    async def test_close_all_reaches_a_socket_by_its_connection_row(self):
        """The only path that addresses sockets individually -- there is no
        group holding all of them."""
        communicator, _ = await self._connect_as(self.moderator)

        names = await database_sync_to_async(close_all_connections)(
            notice=Notice(payload={"type": "warning", "message": "Back at 21:00"})
        )

        self.assertEqual(1, len(names))
        await self._assert_closed(
            communicator, code=GOING_AWAY, notice=("warning", "Back at 21:00")
        )


@ws_test_settings
class CloseAllSelectionTests(TestCase):
    """Which rows close_all_connections picks up. No sockets needed: rows are
    written by the consumer but read by anything."""

    def setUp(self):
        self.dispatch = patch("voteit.messaging.close._dispatch").start()
        self.addCleanup(patch.stopall)

    def test_open_rows_are_addressed(self):
        Connection.objects.create(user_id=1, channel_name="specific.aaa")
        Connection.objects.create(user_id=2, channel_name="specific.bbb")
        self.assertEqual(
            {"specific.aaa", "specific.bbb"},
            set(close_all_connections()),
        )
        self.assertEqual(2, self.dispatch.call_count)

    def test_closed_rows_are_skipped(self):
        Connection.objects.create(user_id=1, channel_name="gone", code=1000)
        self.assertEqual([], close_all_connections())
        self.dispatch.assert_not_called()

    def test_stale_rows_are_skipped(self):
        """Open but silent: almost always a socket that died with its process,
        so sending to it is a write to a queue nobody reads."""
        from datetime import timedelta

        from django.utils.timezone import now

        Connection.objects.create(
            user_id=1,
            channel_name="zombie",
            last_action=now() - timedelta(days=1),
        )
        self.assertEqual([], close_all_connections())
        self.dispatch.assert_not_called()


@ws_test_settings
class CloseSocketsCommandTests(TestCase):
    def setUp(self):
        # _dispatch is the close; the notice goes the ordinary publish route,
        # so MessageCatcher is what sees it.
        self.dispatch = patch("voteit.messaging.close._dispatch").start()
        self.addCleanup(patch.stopall)
        Connection.objects.create(user_id=1, channel_name="specific.aaa")

    def _call(self, *args):
        out = StringIO()
        with MessageCatcher() as messages:
            call_command("close_sockets", *args, stdout=out)
        self.notices = [m for m in messages if m.action == "s.msg"]
        return out.getvalue()

    def test_a_message_is_sent_as_a_notice_before_the_close(self):
        self._call("--message", "Back at 21:00", "--type", "error")
        (notice,) = self.notices
        self.assertEqual("error", notice.payload.type)
        self.assertEqual("Back at 21:00", notice.payload.message)
        self.dispatch.assert_called_once()

    def test_the_notice_type_defaults_to_warning(self):
        self._call("--message", "Restarting")
        self.assertEqual("warning", self.notices[0].payload.type)

    def test_no_message_means_no_notice(self):
        """The close frame says nothing on its own, so an operator who gives no
        message simply disconnects people silently."""
        self._call()
        self.assertEqual([], self.notices)
        self.dispatch.assert_called_once()

    def test_closes_with_going_away_by_default(self):
        """1001 tells the client to come back -- a restart is not a logout."""
        self._call()
        (event,) = self.dispatch.call_args.args
        self.assertEqual(GOING_AWAY, event.payload.code)

    def test_never_flushes_a_session(self):
        """Maintenance is not a logout -- nobody should have to sign in again
        because the server restarted."""
        self._call()
        (event,) = self.dispatch.call_args.args
        self.assertFalse(event.payload.flush_session)

    def test_reports_how_many_it_closed(self):
        Connection.objects.create(user_id=2, channel_name="specific.bbb")
        self.assertIn("Asked 2 socket(s) to close.", self._call())


@ws_test_settings
class SendNoticeCommandTests(TestCase):
    """s.msg on its own -- nothing is closed and nobody is logged out."""

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(title="One", host="one.example.com")
        cls.other_org = Organisation.objects.create(title="Two", host="two.example.com")

    def setUp(self):
        self.dispatch = patch("voteit.messaging.close._dispatch").start()
        self.addCleanup(patch.stopall)

    def _call(self, *args):
        out = StringIO()
        with ChannelMessageCatcher(OrganisationChannel) as messages:
            call_command("send_notice", *args, stdout=out)
        return messages, out.getvalue()

    def test_sends_the_message_and_type(self):
        messages, _ = self._call(
            "--message",
            "Please evacuate",
            "--type",
            "error",
            "--organisation",
            str(self.org.pk),
        )
        (notice,) = messages
        self.assertEqual("s.msg", notice.action)
        self.assertEqual("error", notice.payload.type)
        self.assertEqual("Please evacuate", notice.payload.message)

    def test_type_defaults_to_info(self):
        messages, _ = self._call("--message", "FYI")
        self.assertEqual("info", messages[0].payload.type)

    def test_nothing_is_closed(self):
        self._call("--message", "FYI")
        self.dispatch.assert_not_called()

    def test_without_an_organisation_every_one_is_reached(self):
        _, output = self._call("--message", "FYI")
        self.assertIn("Sent to 2 organisation channel(s).", output)

    def test_an_organisation_narrows_it(self):
        _, output = self._call("--message", "FYI", "--organisation", str(self.org.pk))
        self.assertIn("Sent to 1 organisation channel(s).", output)

    def test_an_unknown_organisation_is_an_error(self):
        """Otherwise a typo publishes to a group nobody is in and reports
        success -- the worst possible outcome for an alert."""
        with self.assertRaisesMessage(CommandError, "No organisation with pk 404"):
            call_command("send_notice", "--message", "FYI", "--organisation", "404")

    def test_message_is_required(self):
        with self.assertRaises(CommandError):
            call_command("send_notice", "--type", "error")
