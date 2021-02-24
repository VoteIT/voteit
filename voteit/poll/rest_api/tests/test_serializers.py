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
