"""broadcast_organisation -- the organisation filter for anything pushed.

Asserted on the channel-layer target rather than on the message, because the
whole point is *who* it reaches: every authenticated socket joins its own
organisation's group while connecting, so the group is the filter.
"""

from __future__ import annotations

from django.test import TestCase

from voteit.core.messages.notice import Notice
from voteit.messaging.testing import MessageCatcher
from voteit.messaging.testing import ws_test_settings
from voteit.organisation.channels import OrganisationChannel
from voteit.organisation.channels import broadcast_organisation
from voteit.organisation.models import Organisation


@ws_test_settings
class BroadcastOrganisationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.one = Organisation.objects.create(title="One", host="one.example.com")
        cls.two = Organisation.objects.create(title="Two", host="two.example.com")

    @staticmethod
    def _notice():
        return Notice(payload={"type": "error", "message": "Please evacuate"})

    def _catch(self):
        """The catcher itself, not the message list __enter__ hands back: what
        is asserted on here is `.targets`."""
        return MessageCatcher()

    @staticmethod
    def _groups(catcher):
        return sorted(target.name for target in catcher.targets)

    def test_one_organisation_reaches_only_its_own_group(self):
        catcher = self._catch()
        with catcher as messages:
            pks = broadcast_organisation(self._notice(), self.one, on_commit=False)
        self.assertEqual([self.one.pk], pks)
        self.assertEqual(
            [OrganisationChannel(self.one.pk).channel_name], self._groups(catcher)
        )
        self.assertEqual(1, len(messages))

    def test_a_bare_pk_works_too(self):
        """Callers hold one or the other; only the pk is ever read."""
        catcher = self._catch()
        with catcher:
            broadcast_organisation(self._notice(), self.one.pk, on_commit=False)
        self.assertEqual(
            [OrganisationChannel(self.one.pk).channel_name], self._groups(catcher)
        )

    def test_no_organisation_reaches_every_one(self):
        catcher = self._catch()
        with catcher:
            pks = broadcast_organisation(self._notice(), on_commit=False)
        self.assertEqual({self.one.pk, self.two.pk}, set(pks))
        self.assertEqual(
            sorted(
                OrganisationChannel(pk).channel_name
                for pk in (self.one.pk, self.two.pk)
            ),
            self._groups(catcher),
        )

    def test_it_is_a_group_publish_not_a_per_socket_send(self):
        """Connection has no organisation column, so the alternative would be a
        subquery through User plus one send per open socket."""
        catcher = self._catch()
        with catcher:
            broadcast_organisation(self._notice(), self.one, on_commit=False)
        self.assertTrue(catcher.targets)
        self.assertTrue(all(target.group for target in catcher.targets))
