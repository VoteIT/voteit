from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from envelope.messages.common import BatchMessage
from envelope.messages.errors import BadRequestError
from envelope.messages.errors import UnauthorizedError
from envelope.testing import ChannelMessageCatcher
from envelope.testing import MessageCatcher
from envelope.testing import testing_channel_layers_setting

from voteit.agenda.messages import AgendaChanged
from voteit.agenda.messages import AgendaDeleted
from voteit.agenda.messages import LastReadChangedSchema
from voteit.agenda.models import AgendaItem
from voteit.agenda.models import LastRead
from voteit.agenda.messages import LastReadChanged
from voteit.agenda.rest_api.serializers import LastReadSerializer
from voteit.agenda.workflows import AgendaItemWf
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.models import Meeting


User = get_user_model()


class LastReadSerializerCompatTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    def test_compat_with_drf(self):
        user = User.objects.get(pk=2)
        ai = AgendaItem.objects.get(pk=1)
        last_read = ai.mark_read(user)
        serializer = LastReadSerializer(last_read)
        pydantics = LastReadChangedSchema(timestamp=last_read.timestamp, agenda_item=1)
        self.assertIsInstance(pydantics.timestamp, str)
        self.assertEqual(pydantics.timestamp, serializer.data["timestamp"])


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class AgendaItemBulkChangeTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.meeting.ongoing()
        cls.meeting.save()
        cls.ai_1: AgendaItem = cls.meeting.agenda_items.get(pk=1)
        cls.ai_2: AgendaItem = cls.meeting.agenda_items.get(pk=2)
        cls.ai_3: AgendaItem = cls.meeting.agenda_items.get(pk=3)
        cls.participant = cls.meeting.participants.get(username="participant")
        cls.moderator = cls.meeting.participants.get(username="moderator")

    def _mk_one(self, user, **kw):
        from voteit.agenda.messages import AgendaItemBulkChange

        kw.setdefault("meeting", 1)

        return AgendaItemBulkChange(
            mm={"user_pk": user.pk, "consumer_name": "abc"}, **kw
        )

    def test_message_job_state(self):
        msg = self._mk_one(
            self.moderator, agenda_items=[1, 2, 3], state=AgendaItemWf.ONGOING
        )
        with ChannelMessageCatcher(ModeratorsChannel, AgendaChanged) as messages:
            msg.run_job()
        self.ai_1.refresh_from_db()
        self.assertEqual(AgendaItemWf.ONGOING, self.ai_1.state)
        self.ai_3.refresh_from_db()
        self.assertEqual(AgendaItemWf.ONGOING, self.ai_3.state)
        self.assertEqual(3, len(messages))

    def test_message_meeting_not_ongoing(self):
        self.meeting.upcoming()
        self.meeting.save()
        msg = self._mk_one(
            self.moderator, agenda_items=[1, 3], state=AgendaItemWf.ONGOING
        )
        with ChannelMessageCatcher(ModeratorsChannel, AgendaChanged) as messages:
            msg.run_job()
        self.ai_1.refresh_from_db()
        self.assertEqual(AgendaItemWf.UPCOMING, self.ai_1.state)
        self.ai_3.refresh_from_db()
        self.assertEqual(AgendaItemWf.PRIVATE, self.ai_3.state)
        self.assertEqual(0, len(messages))

    def test_participant(self):
        msg = self._mk_one(
            self.participant, agenda_items=[1, 3], state=AgendaItemWf.ONGOING
        )
        with self.assertRaises(UnauthorizedError):
            msg.run_job()

    def test_message_job_block(self):
        self.ai_2.block_proposals = True
        self.ai_2.block_discussion = True
        self.ai_2.save()
        msg = self._mk_one(
            self.moderator,
            agenda_items=[1, 2, 3],
            block_proposals=True,
            block_discussion=True,
        )
        with ChannelMessageCatcher(ModeratorsChannel, AgendaChanged) as messages:
            msg.run_job()
        self.ai_1.refresh_from_db()
        self.assertTrue(self.ai_1.block_discussion)
        self.assertTrue(self.ai_1.block_proposals)
        self.ai_3.refresh_from_db()
        self.assertTrue(self.ai_3.block_discussion)
        self.assertTrue(self.ai_3.block_proposals)
        self.assertEqual(2, len(messages))

    def test_all_change_but_no_duplicate_messages(self):
        msg = self._mk_one(
            self.moderator,
            agenda_items=[1, 2, 3],
            block_proposals=True,
            block_discussion=True,
            state=AgendaItemWf.ONGOING,
        )
        with ChannelMessageCatcher(ModeratorsChannel, AgendaChanged) as messages:
            msg.run_job()
        self.assertEqual(3, len(messages))
        response = [x for x in messages if x.data.pk == self.ai_1.pk][0]
        self.assertEqual(
            {
                "pk": self.ai_1.pk,
                "block_discussion": True,
                "block_proposals": True,
                "meeting": 1,
                "state": "ongoing",
                "title": "Pickles",
            },
            response.data.dict(exclude={"related_modified", "tags", "order"}),
        )


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class AgendaItemBulkDeleteTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.participant = cls.meeting.participants.get(username="participant")
        cls.moderator = cls.meeting.participants.get(username="moderator")

    def _mk_one(self, user, **kw):
        from voteit.agenda.messages import AgendaItemBulkDelete

        kw.setdefault("meeting", 1)

        return AgendaItemBulkDelete(
            mm={"user_pk": user.pk, "consumer_name": "abc"}, **kw
        )

    def test_message_job(self):
        msg = self._mk_one(self.moderator, agenda_items=[1, 2, 3])
        with ChannelMessageCatcher(
            MeetingChannel, AgendaDeleted, BatchMessage
        ) as messages:
            msg.run_job()
        self.assertFalse(self.meeting.agenda_items.filter(pk__in=[1, 2, 3]).count())
        self.assertEqual(3, len(messages))
        self.assertEqual({1, 2, 3}, {x.data.pk for x in messages})

    def test_message_meeting_not_ongoing(self):
        self.meeting.ongoing()
        self.meeting.save()
        msg = self._mk_one(self.moderator, agenda_items=[1, 2, 3])
        with self.assertRaises(BadRequestError):
            msg.run_job()
