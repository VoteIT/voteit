from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory

User = get_user_model()


class PollDetailSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create(title="Hello")
        self.poll = self.meeting.polls.create(
            agenda_item=self.ai,
            meeting=self.meeting,
            method_name="simple",
            body="<b>Hello</b>",
            title="world",
        )
        self.prop1 = self.poll.proposals.create()
        self.prop2 = self.poll.proposals.create()

    @property
    def _cut(self):
        from voteit.poll.rest_api.serializers import PollDetailSerializer

        return PollDetailSerializer

    def test_serializer_url(self):
        serializer = self._cut(self.poll)
        self.assertIsNone(serializer.data["url"])

        rf = RequestFactory()
        request = rf.request()
        serializer = self._cut(self.poll, context={"request": request})
        self.assertEqual(
            f"http://testserver/api/polls/{self.poll.pk}/", serializer.data["url"]
        )

    def test_serializer_simple(self):
        serializer = self._cut(self.poll)
        self.assertEqual(
            {
                "pk": self.poll.pk,
                "body": "<b>Hello</b>",
                "title": "world",
                "agenda_item": self.ai.pk,
                "electoral_register": None,
                "initial_electoral_register": None,
                "meeting": self.meeting.pk,
                "method_name": "simple",
                "proposals": [self.prop1.pk, self.prop2.pk],
                "result_data": None,
                "settings_data": None,
                "state": "private",
                "url": None,
            },
            serializer.data,
        )

    def test_serializer_repeated_schulze(self):
        self.poll.method_name = "repeated_schulze"
        self.poll.settings = {"winners": 2}
        prop3 = self.poll.proposals.create()
        serializer = self._cut(self.poll)
        expected_data = serializer.data.copy()
        self.assertEqual(
            {self.prop1.pk, self.prop2.pk, prop3.pk},
            set(expected_data.pop("proposals")),
        )
        self.assertEqual("repeated_schulze", expected_data.pop("method_name"))
        self.assertEqual({"winners": 2}, expected_data.pop("settings_data"))

    def test_schulze_result(self):
        self.poll.method_name = "schulze"
        fake_result = {
            "candidates": {1496, 1494, 1495},
            "winner": 1494,
            "pairs": {
                (1496, 1494): 0,
                (1496, 1495): 0,
                (1494, 1496): 1,
                (1494, 1495): 1,
                (1495, 1496): 1,
                (1495, 1494): 0,
            },
            "strong_pairs": {(1494, 1496): 1, (1494, 1495): 1, (1495, 1496): 1},
        }
        formatted_fake_result = self.poll.method.schulze_to_poll_result(fake_result)
        self.poll.result = formatted_fake_result
        self.poll.save()
        serializer = self._cut(self.poll)
        expected_data = serializer.data.copy()
        result_data = expected_data.pop("result_data")
        self.assertSequenceEqual(
            result_data["candidates"], formatted_fake_result.candidates
        )
        self.assertEqual(len(formatted_fake_result.pairs), len(result_data["pairs"]))
        self.assertSequenceEqual(
            result_data["pairs"][0][0], list(formatted_fake_result.pairs[0][0])
        )
        self.assertEqual(
            len(formatted_fake_result.strong_pairs), len(result_data["strong_pairs"])
        )


class PollCreateSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create(title="Hello")
        self.prop = self.ai.proposals.create()
        self.er = self.meeting.electoral_registers.create()
        self.er.voters.create(username="one")

    @property
    def _cut(self):
        from voteit.poll.rest_api.serializers import PollCreateSerializer

        return PollCreateSerializer

    def _fixture(self, **kw):
        kw.setdefault("meeting", self.meeting.pk)
        kw.setdefault("agenda_item", self.ai.pk)
        kw.setdefault("method_name", "simple")
        kw.setdefault("title", "Well...")
        kw.setdefault("proposals", [self.prop.pk])
        return kw

    def test_serializer_no_props(self):
        data = self._fixture()
        data.pop("proposals")
        serializer = self._cut(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("proposals", serializer.errors)

    def test_serializer_minimal(self):
        data = self._fixture()
        serializer = self._cut(data=data)
        self.assertTrue(serializer.is_valid())
        instance = serializer.save()
        instance.electoral_register = self.er
        instance.upcoming()
        instance.ongoing()
        instance.save()

    def test_serializer_wrong_ai(self):
        other_ai = self.meeting.agenda_items.create()
        other_prop = other_ai.proposals.create()
        data = self._fixture(proposals=[other_prop.pk])
        serializer = self._cut(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("proposals", serializer.errors)

    def test_serializer_repeated_schulze(self):
        prop2 = self.ai.proposals.create()
        prop3 = self.ai.proposals.create()
        data = self._fixture(
            method_name="repeated_schulze",
            proposals=[self.prop.pk, prop2.pk, prop3.pk],
        )
        serializer = self._cut(data=data)
        self.assertTrue(serializer.is_valid())
        instance = serializer.save()
        instance.electoral_register = self.er
        instance.upcoming()
        instance.ongoing()
        instance.save()

    def test_serializer_scottish_stv(self):
        prop2 = self.ai.proposals.create()
        prop3 = self.ai.proposals.create()
        data = self._fixture(
            method_name="scottish_stv",
            proposals=[self.prop.pk, prop2.pk, prop3.pk],
            settings={"winners": 2},
        )
        serializer = self._cut(data=data)
        self.assertTrue(serializer.is_valid())
        instance = serializer.save()
        instance.electoral_register = self.er
        instance.upcoming()
        instance.ongoing()
        instance.save()


class ElectoralRegisterSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.er = self.meeting.electoral_registers.create()
        one = self.er.voters.create(username="one")
        two = self.er.voters.create(username="two")
        self.voter_pks = {one.pk, two.pk}

    @property
    def _cut(self):
        from voteit.poll.rest_api.serializers import ElectoralRegisterSerializer

        return ElectoralRegisterSerializer

    def test_er(self):
        serializer = self._cut(self.er)
        self.assertEqual(self.er.pk, serializer.data["pk"])
        self.assertEqual(self.voter_pks, set(serializer.data["voters"]))
        self.assertEqual(None, serializer.data["url"])

    def test_er_with_url(self):
        rf = RequestFactory()
        request = rf.request()
        serializer = self._cut(self.er, context={"request": request})
        self.assertEqual(
            f"http://testserver/api/electoral-registers/{self.er.pk}/",
            serializer.data["url"],
        )
