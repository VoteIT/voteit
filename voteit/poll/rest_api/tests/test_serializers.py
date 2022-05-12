from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory

User = get_user_model()


class PollDetailSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        cls.meeting: Meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create(title="Hello")
        cls.poll = cls.meeting.polls.create(
            agenda_item=cls.ai,
            meeting=cls.meeting,
            method_name="simple",
            body="<b>Hello</b>",
            title="world",
        )
        cls.prop1 = cls.poll.proposals.create()
        cls.prop2 = cls.poll.proposals.create()

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

    def test_serializer_readonly_fields(self):
        serializer = self._cut(self.poll, data={"title": "No no"})
        serializer.is_valid()  # Why the f...
        inst = serializer.save()
        self.assertEqual("world", inst.title)

    def test_serializer_simple(self):
        serializer = self._cut(self.poll)
        data = serializer.data
        data.pop("started")
        data.pop("closed")
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
                "result": None,
                "settings": None,
                "state": "private",
                "url": None,
                "abstain_count": None,
            },
            data,
        )

        def test_serializer_simple_finished(self):
            self.poll.abstains = 5
            self.poll.save()
            serializer = self._cut(self.poll)
            data = serializer.data
            data.pop("started")
            data.pop("closed")
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
                    "result": None,
                    "settings": None,
                    "state": "private",
                    "url": None,
                    "abstain_count": 5,
                },
                data,
            )

    def test_serializer_repeated_schulze(self):
        self.poll.method_name = "repeated_schulze"
        # reset cache
        self.poll.method = self.poll.get_method_class()(self.poll)
        self.poll.settings = {"winners": 2}
        prop3 = self.poll.proposals.create()
        serializer = self._cut(self.poll)
        expected_data = serializer.data.copy()
        self.assertEqual(
            {self.prop1.pk, self.prop2.pk, prop3.pk},
            set(expected_data.pop("proposals")),
        )
        self.assertEqual("repeated_schulze", expected_data.pop("method_name"))
        self.assertEqual(
            {"deny_proposal": False, "stars": 5, "winners": 2},
            expected_data.pop("settings"),
        )

    def test_schulze_result(self):
        self.poll.method_name = "schulze"
        # reset cache object
        self.poll.method = self.poll.get_method_class()(self.poll)
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
        result = expected_data.pop("result")
        self.assertSequenceEqual(result["candidates"], formatted_fake_result.candidates)
        self.assertEqual(len(formatted_fake_result.pairs), len(result["pairs"]))
        self.assertSequenceEqual(
            result["pairs"][0][0], list(formatted_fake_result.pairs[0][0])
        )
        self.assertEqual(
            len(formatted_fake_result.strong_pairs), len(result["strong_pairs"])
        )


class PollCreateSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create(title="Hello")
        self.prop = self.ai.proposals.create()
        self.er = self.meeting.electoral_registers.create()
        self.voter = self.er.voters.create(username="one")

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

    def test_serializer_wrong_method(self):
        data = self._fixture(method_name="404")
        serializer = self._cut(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("method_name", serializer.errors)

    def test_serializer_historic_method(self):
        data = self._fixture(method_name="schulze_pr")
        serializer = self._cut(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("method_name", serializer.errors)
        self.assertIn("historic", str(serializer.errors["method_name"][0]))

    def test_settings_with_no_settings_method(self):
        data = self._fixture(settings={"weee": "okay"})
        serializer = self._cut(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("settings", serializer.errors)

    def test_bad_settings(self):
        data = self._fixture(
            settings={"winners": "yes please"}, method_name="repeated_schulze"
        )
        serializer = self._cut(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("settings", serializer.errors)

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

    def test_serializer_repeated_schulze_with_deny(self):
        prop2 = self.ai.proposals.create()
        data = self._fixture(
            method_name="repeated_schulze",
            settings={"deny_proposal": True},
            proposals=[self.prop.pk, prop2.pk],
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

    def test_serializer_start(self):
        self.meeting.er_policy_name = "auto_always"
        self.meeting.save()
        self.meeting.add_roles(self.voter, "potential_voter")
        data = self._fixture(start=True)
        serializer = self._cut(data=data)
        self.assertTrue(serializer.is_valid())
        instance = serializer.save()
        self.assertEqual("ongoing", instance.state)


class ElectoralRegisterSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.er = self.meeting.electoral_registers.create()
        self.one = self.er.voters.create(username="one")
        self.two = self.er.voters.create(username="two")

    @property
    def _cut(self):
        from voteit.poll.rest_api.serializers import ElectoralRegisterSerializer

        return ElectoralRegisterSerializer

    def test_er(self):
        serializer = self._cut(self.er)
        data = serializer.data
        self.assertEqual(self.er.pk, data.pop("pk"))
        self.assertEqual(
            [{"user": self.one.pk, "weight": 1}, {"user": self.two.pk, "weight": 1}],
            sorted(data.pop("weights"), key=lambda x: x["user"]),
        )
        self.assertIsNotNone(data.pop("created"))
        self.assertEqual(self.meeting.pk, data.pop("meeting"))
        self.assertFalse(data)


class VoteSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        cls.meeting = Meeting.objects.create()
        cls.er = cls.meeting.electoral_registers.create()
        cls.ai = cls.meeting.agenda_items.create(title="Hello")
        cls.poll = cls.meeting.polls.create(
            agenda_item=cls.ai,
            meeting=cls.meeting,
            method_name="simple",
            body="<b>Hello</b>",
            title="world",
            electoral_register=cls.er,
        )
        cls.prop = cls.poll.proposals.create()
        cls.user = cls.er.voters.create(username="voter")
        cls.vote = cls.poll.votes.create(user=cls.user, vote="yes")

    @property
    def _cut(self):
        from voteit.poll.rest_api.serializers import VoteSerializer

        return VoteSerializer

    def test_serializer(self):
        serializer = self._cut(self.vote)
        data = serializer.data
        self.assertEqual(self.vote.pk, data.pop("pk"))
        self.assertEqual(self.vote.user.pk, data.pop("user"))
        self.assertEqual(self.vote.poll.pk, data.pop("poll"))
        self.assertEqual(self.vote.abstain, data.pop("abstain"))
        self.assertEqual({"choice": "yes"}, data.pop("vote"))
