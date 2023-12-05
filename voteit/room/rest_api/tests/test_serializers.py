from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.room.models import Room


class CreateRoomSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()

    @property
    def _cut(self):
        from voteit.room.rest_api.serializers import CreateRoomSerializer

        return CreateRoomSerializer

    def test_create(self):
        serializer = self._cut(data={"meeting": self.meeting.pk})
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        instance = serializer.save()
        self.assertIsInstance(instance, Room)


class RoomDetailSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.room: Room = cls.meeting.rooms.create()
        cls.sls = cls.meeting.speaker_systems.create(
            method_name="simple", room=cls.room
        )
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop1 = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.prop3 = cls.ai.proposals.create()
        cls.room = cls.meeting.rooms.create()

    @property
    def _cut(self):
        from voteit.room.rest_api.serializers import RoomDetailSerializer

        return RoomDetailSerializer

    def test_serialize(self):
        instance = self.meeting.rooms.create(sls=self.sls, title="Hello")
        serializer = self._cut(instance)
        data = serializer.data
        self.assertTrue(data.pop("pk"))
        self.assertTrue(data.pop("created", False))
        self.assertEqual(
            {
                "meeting": self.meeting.pk,
                "open": False,
                "title": "Hello",
                "body": "",
                "send_sls": False,
                "send_proposals": False,
                "handler": None,
                "show_time": True,
                "agenda_item": None,
                "poll": None,
                "show_ballot": False,
            },
            data,
        )


class RoomHandleSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.room = cls.meeting.rooms.create()
        cls.sls = cls.meeting.speaker_systems.create(
            method_name="simple", room=cls.room
        )
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop1 = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.prop3 = cls.ai.proposals.create()
        cls.room = cls.meeting.rooms.create()

    @property
    def _cut(self):
        from voteit.room.rest_api.serializers import RoomHandleSerializer

        return RoomHandleSerializer

    def test_no_highlighted(self):
        self.room.highlighted_proposals.create(proposal=self.prop2)
        serializer = self._cut(self.room, data={"highlighted": []}, partial=True)
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertFalse(self.room.highlighted_proposal_pks)

    def test_with_highlight(self):
        serializer = self._cut(
            self.room,
            data={"highlighted": [self.prop2.pk, self.prop1.pk]},
            partial=True,
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        serializer.save()
        self.assertEqual(
            [self.prop2.pk, self.prop1.pk], list(self.room.highlighted_proposal_pks)
        )

    def test_bad_values(self):
        serializer = self._cut(
            self.room,
            data={"highlighted": [-1, self.prop1.pk]},
            partial=True,
        )
        serializer.is_valid()
        self.assertEqual({"highlighted"}, set(serializer.errors))
        self.assertEqual(
            "The following proposals don't exist withing this meeting: -1",
            str(serializer.errors["highlighted"][0]),
        )

    def test_bad_values_proposal_from_another_meeting(self):
        new_meeting = Meeting.objects.create()
        new_ai = new_meeting.agenda_items.create()
        new_prop = new_ai.proposals.create()
        serializer = self._cut(
            self.room,
            data={"highlighted": [new_prop.pk, self.prop1.pk]},
            partial=True,
        )
        serializer.is_valid()
        self.assertEqual({"highlighted"}, set(serializer.errors))
        self.assertEqual(
            f"The following proposals don't exist withing this meeting: {new_prop.pk}",
            str(serializer.errors["highlighted"][0]),
        )


class RoomHighlightedSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop1 = cls.ai.proposals.create()
        cls.prop2 = cls.ai.proposals.create()
        cls.prop3 = cls.ai.proposals.create()
        cls.room = cls.meeting.rooms.create()
        cls.sls = cls.meeting.speaker_systems.create(
            method_name="simple", room=cls.room
        )
        cls.room = cls.meeting.rooms.create()

    @property
    def _cut(self):
        from voteit.room.rest_api.serializers import RoomHighlightedSerializer

        return RoomHighlightedSerializer

    def test_no_highlighted(self):
        self.assertEqual(
            {"pk": self.room.pk, "highlighted": []},
            self._cut(self.room).data,
        )

    def test_some_selected(self):
        self.room.highlighted_proposals.create(proposal=self.prop2)
        self.room.highlighted_proposals.create(proposal=self.prop1)
        self.room.save()
        self.assertEqual(
            {
                "pk": self.room.pk,
                "highlighted": [self.prop2.pk, self.prop1.pk],
            },
            self._cut(self.room).data,
        )
