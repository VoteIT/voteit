from __future__ import annotations

from json import loads
from typing import TYPE_CHECKING
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from envelope.utils import channel_layer

from voteit.invites.channels import MeetingInvitesChannel
from voteit.invites.messages import MeetingInviteAdded
from voteit.invites.messages import MeetingInviteChanged
from voteit.invites.models import MeetingInvite
from voteit.invites.testing import get_unvalidated_fixture_content
from voteit.invites.utils import get_invite_adapter_registry
from voteit.invites.workflows import InviteWf
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.organisation.models import Organisation

if TYPE_CHECKING:
    from voteit.invites.messages import AddInvites

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AddInvitesTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)

    @property
    def _cut(self):
        from voteit.invites.messages import AddInvites

        return AddInvites

    def _mk_one(self, user_pk: int = None, **kw) -> AddInvites:
        if user_pk is None:
            user_pk = 1  # Moderator from fixture
        kw.setdefault("meeting", 1)  # from fixture
        return self._cut(mm={"consumer_name": "abc", "user_pk": user_pk}, **kw)

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_add(self, mock_publish):
        data = []
        for name in ["one", "two", "three"]:
            data.append(f"{name}@betahaus.net")
        msg = self._mk_one(rows=data, columns=["email"], roles=[str(ROLE_PARTICIPANT)])
        with self.captureOnCommitCallbacks(execute=True):
            response = msg.run_job()
        self.assertEqual({"added": 3, "changed": 0, "existed": 0}, response.data.dict())
        # Check pushes
        self.assertTrue(mock_publish.called)
        self.assertEqual(3, len(mock_publish.mock_calls))
        emails = {
            x.args[0].data.user_data.get("email") for x in mock_publish.mock_calls
        }
        self.assertEqual(
            {"one@betahaus.net", "two@betahaus.net", "three@betahaus.net"}, emails
        )

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_add_modifies_already_existing_invites(self, mock_publish):
        meeting = self.meeting
        moderator = User.objects.get(username="moderator")
        diffing_data_invite: MeetingInvite = meeting.invites.create(
            user_data={"email": "one@betahaus.net"},
            roles=["voter"],
        )
        # Will be changed too
        rejected_invite: MeetingInvite = meeting.invites.create(
            user_data={"email": "two@betahaus.net"},
            roles=["participant", "voter"],
            state=InviteWf.REJECTED,
        )
        mock_publish.reset_mock()
        data = []
        for name in ["one", "two", "three"]:
            data.append(f"{name}@betahaus.net")
        msg = self._mk_one(
            user_pk=moderator.pk,
            rows=data,
            columns=["email"],
            roles=[str(ROLE_PARTICIPANT)],
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = msg.run_job()
        self.assertEqual({"added": 1, "changed": 2, "existed": 0}, response.data.dict())
        # Check pushes
        self.assertTrue(mock_publish.called)
        self.assertEqual(3, len(mock_publish.mock_calls))
        changed_msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(changed_msg, MeetingInviteChanged)
        self.assertEqual([ROLE_PARTICIPANT], changed_msg.data.roles)
        added_msg = mock_publish.mock_calls[2].args[0]
        self.assertIsInstance(added_msg, MeetingInviteAdded)

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_add_partial_match(self, mock_publish):
        moderator = User.objects.get(username="moderator")
        multi_invite: MeetingInvite = self.meeting.invites.create(
            user_data={"email": "one@betahaus.net", "swedish_ssn": "121212-1212"},
            roles=[ROLE_POTENTIAL_VOTER],  # This will change
        )
        mock_publish.reset_mock()
        data = []
        for name in ["one", "two", "three"]:
            data.append(f"{name}@betahaus.net")
        msg = self._mk_one(
            user_pk=moderator.pk,
            rows=data,
            columns=["email"],
            roles=[str(ROLE_PARTICIPANT)],
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = msg.run_job()
        self.assertEqual({"added": 2, "changed": 1, "existed": 0}, response.data.dict())
        # Check pushes
        self.assertTrue(mock_publish.called)
        self.assertEqual(3, len(mock_publish.mock_calls))
        multi_invite.refresh_from_db()
        self.assertEqual([ROLE_PARTICIPANT], multi_invite.roles)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ClearInviteAnnotationsTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.org = Organisation.objects.get(pk=1)
        cls.din = cls.org.users.create(username="din", email="vader@betahaus.net")
        cls.luke = cls.org.users.create(username="luke", email="luke@betahaus.net")
        cls.vader = cls.org.users.create(username="vader", email="vader@betahaus.net")
        # Invite fixture
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        cls.registry = get_invite_adapter_registry()
        invite_data = list(cls.registry.build_ud_query_seq(columns, rows))
        cls.meeting.invites.create_or_update_mixed(
            data=invite_data, roles=[ROLE_PARTICIPANT], meeting=cls.meeting
        )
        cls.inv_din: MeetingInvite = MeetingInvite.objects.get(
            user_data={"email": "din@betahaus.net"}
        )
        cls.inv_vader: MeetingInvite = MeetingInvite.objects.get(
            user_data={"email": "vader@betahaus.net"}
        )
        cls.inv_luke: MeetingInvite = MeetingInvite.objects.get(
            user_data={"email": "luke@betahaus.net"}
        )
        # A very unrelated invite
        cls.unrelated_inv = cls.meeting.invites.create(
            user_data={"email": "hello@world.com"}
        )
        # Groups
        cls.group_sabreclub = cls.meeting.groups.create(groupid="sabreclub")
        cls.group_sw = cls.meeting.groups.create(groupid="sw")
        cls.role_sith = cls.meeting.group_roles.create(role_id="sith")
        cls.role_jedi = cls.meeting.group_roles.create(role_id="jedi")
        # And annotations
        for _ in cls.registry.run_annotations(
            columns=columns,
            rows=rows,
            invites_qs=cls.meeting.invites.all(),
            meeting=cls.meeting,
        ):
            ...

    @property
    def _cut(self):
        from voteit.invites.messages import ClearInviteAnnotations

        return ClearInviteAnnotations

    def _mk_one(self, user_pk: int = 1, **kw):
        kw.setdefault("meeting", 1)  # from fixture
        return self._cut(mm={"consumer_name": "abc", "user_pk": user_pk}, **kw)

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_clear_groups(self, mock_publish):
        msg = self._mk_one(types=["group"])
        with self.captureOnCommitCallbacks(execute=True):
            response = msg.run_job()
        self.assertTrue(mock_publish.called)
        messages = [
            x.args[0]
            for x in mock_publish.mock_calls
            if x.args[0].name == MeetingInviteChanged.name
        ]
        pks = {x.data.pk for x in messages}
        # Unrelated invite must not be here
        self.assertEqual({self.inv_din.pk, self.inv_luke.pk, self.inv_vader.pk}, pks)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AddInviteAnnotationsTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.org = Organisation.objects.get(pk=1)
        cls.din = cls.org.users.create(username="din", email="vader@betahaus.net")
        cls.luke = cls.org.users.create(username="luke", email="luke@betahaus.net")
        cls.vader = cls.org.users.create(username="vader", email="vader@betahaus.net")
        # Invite fixture
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        cls.registry = get_invite_adapter_registry()
        invite_data = list(cls.registry.build_ud_query_seq(columns, rows))
        cls.meeting.invites.create_or_update_mixed(
            data=invite_data, roles=[ROLE_PARTICIPANT], meeting=cls.meeting
        )
        cls.inv_din: MeetingInvite = MeetingInvite.objects.get(
            user_data={"email": "din@betahaus.net"}
        )
        cls.inv_vader: MeetingInvite = MeetingInvite.objects.get(
            user_data={"email": "vader@betahaus.net"}
        )
        cls.inv_luke: MeetingInvite = MeetingInvite.objects.get(
            user_data={"email": "luke@betahaus.net"}
        )
        # A very unrelated invite
        cls.unrelated_inv = cls.meeting.invites.create(
            user_data={"email": "hello@world.com"}
        )
        # Groups
        cls.group_sabreclub = cls.meeting.groups.create(groupid="sabreclub")
        cls.group_sw = cls.meeting.groups.create(groupid="sw")
        cls.role_sith = cls.meeting.group_roles.create(role_id="sith")
        cls.role_jedi = cls.meeting.group_roles.create(role_id="jedi")

    @property
    def _cut(self):
        from voteit.invites.messages import AddInviteAnnotations

        return AddInviteAnnotations

    def _mk_one(self, user_pk: int = 1, **kw):
        kw.setdefault("meeting", 1)  # from fixture
        return self._cut(mm={"consumer_name": "abc", "user_pk": user_pk}, **kw)

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_invite_updated_msg_sent(self, mock_publish):
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        msg = self._mk_one(rows=rows, columns=columns)
        with self.captureOnCommitCallbacks(execute=True):
            msg.run_job()

        self.assertTrue(mock_publish.called)
        messages = [
            x.args[0]
            for x in mock_publish.mock_calls
            if x.args[0].name == MeetingInviteChanged.name
        ]
        pks = {x.data.pk for x in messages}
        # Unrelated invite must not be here
        self.assertEqual({self.inv_din.pk, self.inv_luke.pk, self.inv_vader.pk}, pks)
        self.assertEqual({True}, {x.data.has_annotations for x in messages})

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_invite_updated_msg_not_sent_if_not_new(self, mock_publish):
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        msg = self._mk_one(rows=rows, columns=columns)
        with self.captureOnCommitCallbacks(execute=True):
            msg.run_job()
        mock_publish.reset_mock()

        # Only vader updated this time
        self.inv_vader.group_annotations.all().delete()
        with self.captureOnCommitCallbacks(execute=True):
            msg.run_job()

        self.assertTrue(mock_publish.called)
        messages = [
            x.args[0]
            for x in mock_publish.mock_calls
            if x.args[0].name == MeetingInviteChanged.name
        ]
        pks = {x.data.pk for x in messages}
        # Unrelated invite must not be here
        self.assertEqual({self.inv_vader.pk}, pks)
        self.assertEqual({True}, {x.data.has_annotations for x in messages})

    @patch.object(channel_layer, "send")  # Probably better to patch elsewhere later on
    def test_progress_messages_sent(self, mock_send):
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        msg = self._mk_one(rows=rows, columns=columns)
        with self.captureOnCommitCallbacks(execute=True):
            msg.run_job()

        self.assertTrue(mock_send.called)
        messages = [loads(x.args[1]["text_data"]) for x in mock_send.mock_calls]
        self.assertEqual(2, len(messages))
        self.assertEqual({"curr": 0, "total": 1, "msg": None}, messages[0]["p"])
        ann_data = messages[1]["p"]
        self.assertEqual(1, ann_data["curr"])
        self.assertEqual(1, ann_data["total"])

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_too_many_columns_in_data_rows(self, mock_publish):
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        msg = self._mk_one(rows=rows, columns=columns)
        with self.captureOnCommitCallbacks(execute=True):
            msg.run_job()
        mock_publish.reset_mock()
        # Make bad data...
        rows[0].append("too much data")
        msg = self._mk_one(rows=rows, columns=columns)
        with self.captureOnCommitCallbacks(execute=True):
            msg.run_job()
