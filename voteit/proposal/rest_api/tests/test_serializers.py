from datetime import datetime

from django.test import RequestFactory
from django.test import TestCase

from voteit.core.testing import mk_hashtag


class GenericProposalSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.agenda.models import AgendaItem
        from voteit.meeting.models import Meeting
        from voteit.proposal.models import Proposal
        from voteit.proposal.models import DiffProposal
        from voteit.proposal.models import TextParagraph
        from voteit.proposal.models import TextDocument

        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.ai: AgendaItem = cls.meeting.agenda_items.create()
        cls.prop: Proposal = Proposal.objects.create(agenda_item=cls.ai)
        cls.text_doc: TextDocument = cls.ai.text_documents.create(
            body="I am the eggman\nI am the walrus"
        )
        cls.paragraph: TextParagraph = cls.text_doc.text_paragraphs.first()
        cls.diff_prop: DiffProposal = cls.paragraph.proposals.create(agenda_item=cls.ai)

    @property
    def _cut(self):
        from voteit.proposal.rest_api.serializers import GenericProposalSerializer

        return GenericProposalSerializer

    def test_serializer_from_queryset(self):
        items = sorted(
            self.ai.proposals.all().select_subclasses(), key=lambda x: x.name
        )
        results = []
        for inst in items:
            results.append(self._cut(inst).data)
        self.assertEqual(2, len(results))
        diff_result = results[0]
        prop_result = results[1]
        self.assertEqual("diff_proposal", diff_result["name"])
        self.assertEqual("proposal", prop_result["name"])
        self.assertEqual(self.paragraph.pk, diff_result["paragraph"])
        self.assertNotIn("paragraph", prop_result)


class ProposalDetailSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.group = self.meeting.groups.create()
        self.user = self.meeting.participants.create(username="jane")
        self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        tag_html = mk_hashtag("world")
        self.prop = self.ai.proposals.create(
            author=self.user,
            body=f"Hello {tag_html}",
            meeting_group=self.group,
            tags=["world"],
        )

    @property
    def _cut(self):
        from voteit.proposal.rest_api.serializers import ProposalDetailSerializer

        return ProposalDetailSerializer

    def test_get(self):
        serializer = self._cut(self.prop)
        data = serializer.data
        self.assertEqual(data.pop("pk"), self.prop.pk)
        self.assertIn("Hello", data.pop("body"))
        self.assertEqual(data.pop("agenda_item"), self.ai.pk)
        dt = datetime.strptime(data.pop("created"), "%Y-%m-%dT%H:%M:%S.%f%z")
        self.assertIsInstance(dt, datetime)
        self.assertEqual(data.pop("author"), self.user.pk)
        prop_id = data.pop("prop_id")
        tags = data.pop("tags")
        self.assertIn(prop_id, tags)
        self.assertIn("world", tags)
        self.assertEqual(2, len(tags))
        self.assertIsInstance(prop_id, str)
        self.assertEqual("published", data.pop("state"))
        self.assertEqual(self.group.pk, data.pop("meeting_group"))
        self.assertEqual([], data.pop("mentions"))
        self.assertEqual("proposal", data.pop("name"))
        # Make sure we checked everything
        self.assertFalse(data.keys())

    def test_patch(self):
        serializer = self._cut(self.prop, {"body": "Bye!", "tags": []}, partial=True)
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.assertEqual(self.prop.body, "Bye!")
        self.assertEqual(1, len(self.prop.tags))  # prop_id is still there


class ProposalCreateSerializer(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.user = self.meeting.participants.create(username="jane")
        self.group = self.meeting.groups.create()
        self.group.members.add(self.user)
        self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")

    @property
    def _cut(self):
        from voteit.proposal.rest_api.serializers import ProposalCreateSerializer

        return ProposalCreateSerializer

    def test_create(self):
        rf = RequestFactory()
        request = rf.request()
        request.user = self.user
        data = {
            "body": "Hello " + mk_hashtag("world"),
            "agenda_item": self.ai.pk,
            "meeting_group": self.group.pk,
        }
        serializer = self._cut(data=data, context={"request": request})
        self.assertTrue(serializer.is_valid())
        instance = serializer.save()
        self.assertIn("world", instance.tags)
        self.assertIn(instance.prop_id, instance.tags)
        self.assertEqual(self.ai, instance.agenda_item)
        self.assertEqual(self.user, instance.author)
        self.assertEqual(self.group, instance.meeting_group)


class DiffProposalDetailSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.agenda.models import AgendaItem
        from voteit.proposal.models import TextParagraph
        from voteit.proposal.models import TextDocument
        from voteit.proposal.models import DiffProposal

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(
            state="ongoing", title="Ongoing"
        )
        cls.text_doc: TextDocument = cls.ai.text_documents.create(
            body="I am the eggman\nI am the walrus"
        )
        cls.para: TextParagraph = cls.text_doc.text_paragraphs.first()
        cls.diff_prop: DiffProposal = cls.para.proposals.create(
            body="I am the eggman\nI am some kind of mamal"
        )

    @property
    def _cut(self):
        from voteit.proposal.rest_api.serializers import DiffProposalDetailSerializer

        return DiffProposalDetailSerializer

    def test_get(self):
        serializer = self._cut(self.diff_prop)
        data = serializer.data
        self.assertEqual(self.diff_prop.pk, data["pk"])
        self.assertEqual(self.diff_prop.body, data["body"])
        self.assertEqual(
            'I am the eggman <br/> I am <span class="text-diff-removed">the walrus</span> <span class="text-diff-added">some kind of mamal</span>',
            data["body_diff"],
        )


class TextDocumentSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.agenda.models import AgendaItem
        from voteit.proposal.models import TextDocument

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(
            state="ongoing", title="Ongoing"
        )
        cls.text_doc: TextDocument = cls.ai.text_documents.create(
            body="I am the eggman\n\nI am the walrus", base_tag="hi"
        )

    @property
    def _cut(self):
        from voteit.proposal.rest_api.serializers import TextDocumentSerializer

        return TextDocumentSerializer

    def test_get(self):
        serializer = self._cut(self.text_doc)
        data = serializer.data
        self.assertEqual(self.text_doc.pk, data["pk"])
        self.assertEqual(self.text_doc.body, data["body"])
        self.assertEqual(2, len(data["paragraphs"]))
        self.assertEqual("hi-1", data["paragraphs"][0]["tag"])
        self.assertEqual("I am the eggman", data["paragraphs"][0]["body"])
