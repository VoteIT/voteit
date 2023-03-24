from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from pydantic import ValidationError

from envelope.messages.errors import UnauthorizedError
from envelope.utils import channel_layer
from voteit.core.testing import FakeCommit
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class CloneMeetingTests(TestCase):
    fixtures = [
        "meeting_test_fixture",
        "agenda_test_fixture",
    ]  # Not full fixture, it's tested in other places

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.org_manager = User.objects.get(username="org_manager")
        cls.moderator = User.objects.get(username="moderator")
        # Managers must be able to read meetings if they want to copy them!
        cls.meeting.add_roles(cls.org_manager, ROLE_PARTICIPANT)

    @property
    def _cut(self):
        from voteit.meeting.messages import CopyMeeting

        return CopyMeeting

    def _mk_one(self, user, **kw):
        kw.setdefault("meeting", self.meeting.pk)
        return self._cut(
            mm={"user_pk": user.pk, "consumer_name": "abc", "id": "copy"}, **kw
        )

    def test_copy_moderator(self):
        msg = self._mk_one(self.moderator)
        with self.assertRaises(UnauthorizedError):
            msg.run_job()

    def test_copy_org_manager(self):
        msg = self._mk_one(self.org_manager)
        with patch.object(channel_layer, "send") as mocked_send:
            with FakeCommit():
                msg.run_job()
                self.assertEqual(1, len(mocked_send.mock_calls))
                self.assertEqual(
                    {
                        "text_data": '{"t": "s.stat", "p": null, "i": "copy", "s": "r"}',
                        "type": "websocket.send",
                        "i": "copy",
                        "t": "s.stat",
                        "s": "r",
                    },
                    mocked_send.mock_calls[0].args[1],
                )
            # Committed here
            self.assertEqual(2, len(mocked_send.mock_calls))
            self.assertEqual(
                {
                    "text_data": '{"t": "s.stat", "p": null, "i": "copy", "s": "s"}',
                    "type": "websocket.send",
                    "i": "copy",
                    "t": "s.stat",
                    "s": "s",
                },
                mocked_send.mock_calls[1].args[1],
            )


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class CreateMeetingGroupsTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.existing_group = cls.meeting.groups.create(title="A", groupid="a")

    @property
    def _cut(self):
        from voteit.meeting.messages import CreateMeetingGroups

        return CreateMeetingGroups

    def _mk_one(self, user, **kw):
        kw.setdefault("meeting", self.meeting.pk)
        return self._cut(
            mm={"user_pk": user.pk, "consumer_name": "abc", "id": "copy"}, **kw
        )

    def test_participant(self):
        msg = self._mk_one(self.participant, groups=[{"title": "B", "groupid": "b"}])
        with self.assertRaises(UnauthorizedError):
            msg.run_job()

    def test_create(self):
        msg = self._mk_one(
            self.moderator,
            groups=[
                {"title": "B", "groupid": "B"},  # <-Transformed
                {"title": "Aha", "groupid": "a", "votes": 1},  # <- Updated
            ],
        )
        with self.captureOnCommitCallbacks(execute=True):
            msg.run_job()
        self.assertEqual(
            [
                {"groupid": "a", "title": "Aha", "votes": 1},
                {"groupid": "b", "title": "B", "votes": None},
            ],
            list(
                self.meeting.groups.all()
                .order_by("pk")
                .values("title", "groupid", "votes")
            ),
        )

    def test_duplicate_group_id(self):
        msg = self._mk_one(
            self.moderator,
            groups=[
                {"title": "a", "groupid": "a"},
                {
                    "title": "B",
                    "groupid": "A",
                },  # <- Duplicate group id, since lowercased
            ],
        )
        with self.assertRaises(ValidationError) as cm:
            msg.run_job()
        self.assertEqual(
            [
                {
                    "loc": ("groups",),
                    "msg": "There were errors with groups:\nThese lines have groupids that aren't unique: 2\n",
                    "type": "value_error",
                }
            ],
            cm.exception.errors(),
        )

    def test_duplicate_title(self):
        msg = self._mk_one(
            self.moderator,
            groups=[
                {"title": "a", "groupid": "a"},
                {
                    "title": "A",
                    "groupid": "b",
                },  # <- Duplicate title since checked with lowercase
            ],
        )
        with self.assertRaises(ValidationError) as cm:
            msg.run_job()
        self.assertEqual(
            [
                {
                    "loc": ("groups",),
                    "msg": "There were errors with groups:\nThese lines have titles that aren't unique: 2\n",
                    "type": "value_error",
                }
            ],
            cm.exception.errors(),
        )
