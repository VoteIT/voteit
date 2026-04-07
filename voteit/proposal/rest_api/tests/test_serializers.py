from __future__ import annotations
from datetime import datetime

from django.test import RequestFactory
from django.test import TestCase
from typing import TYPE_CHECKING

from voteit.agenda.models import AgendaItem
from voteit.core.testing import mk_hashtag
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.proposal.models import Proposal
from voteit.proposal.models import TextDocument
from voteit.proposal.models import TextParagraph

if TYPE_CHECKING:
    from voteit.proposal.models import DiffProposal


class GenericProposalSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
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
        self.assertEqual(self.prop.pk, prop_result["pk"])
        self.assertEqual(self.diff_prop.pk, diff_result["pk"])
        self.assertEqual(self.paragraph.pk, diff_result["paragraph"])
        self.assertNotIn("paragraph", prop_result)


class ProposalDetailSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.group = cls.meeting.groups.create()
        cls.user = cls.meeting.participants.create(username="jane")
        cls.ai = cls.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        tag_html = mk_hashtag("world")
        cls.prop = cls.ai.proposals.create(
            author=cls.user,
            body=f"Hello {tag_html}",
            meeting_group=cls.group,
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
        dt = datetime.strptime(data.pop("modified"), "%Y-%m-%dT%H:%M:%S.%f%z")
        self.assertIsInstance(dt, datetime)
        self.assertFalse(data.pop("as_group"))
        self.assertEqual("proposal", data.pop("shortname"))
        # Make sure we checked everything
        self.assertFalse(data.keys())

    def test_patch(self):
        serializer = self._cut(self.prop, {"body": "Bye!", "tags": []}, partial=True)
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.assertEqual(self.prop.body, "Bye!")
        self.assertEqual(1, len(self.prop.tags))  # prop_id is still there


class ProposalCreateSerializer(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.user = cls.meeting.participants.create(username="user")
        cls.group = cls.meeting.groups.create()
        cls.group.members.add(cls.user)
        cls.non_group_user = cls.meeting.participants.create(username="non_group_user")
        cls.meeting.add_roles(cls.user, ROLE_PROPOSER)
        cls.meeting.add_roles(cls.non_group_user, ROLE_PROPOSER)
        cls.ai = cls.meeting.agenda_items.create(state="ongoing", title="Ongoing")

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

    def test_create_agenda_reqiured(self):
        rf = RequestFactory()
        request = rf.request()
        request.user = self.user
        data = {
            "body": "Hello " + mk_hashtag("world"),
            "meeting_group": self.group.pk,
        }
        serializer = self._cut(data=data, context={"request": request})
        serializer.is_valid()
        self.assertIn("agenda_item", serializer.errors)

    def test_create_with_wrong_group(self):
        rf = RequestFactory()
        request = rf.request()
        request.user = self.non_group_user
        data = {
            "body": "Hello " + mk_hashtag("world"),
            "agenda_item": self.ai.pk,
            "meeting_group": self.group.pk,
        }
        serializer = self._cut(data=data, context={"request": request})
        serializer.is_valid()
        self.assertIn("meeting_group", serializer.errors)


class DiffProposalDetailSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
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
            body="I am the eggman\nI am some kind of mamal",
            agenda_item=cls.ai,
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
        self.assertEqual(self.diff_prop.as_group, data["as_group"])
        self.assertEqual("diff_proposal", data["shortname"])
        self.assertEqual(
            'I am the eggman <br/> I am <span class="text-diff-removed">the walrus</span> <span class="text-diff-added">some kind of mamal</span>',
            data["body_diff_brief"],
        )

    def test_patch(self):
        serializer = self._cut(
            self.diff_prop, data={"body": "Hello world"}, partial=True
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)

    def test_patch_identical(self):
        serializer = self._cut(
            self.diff_prop, data={"body": self.para.body}, partial=True
        )
        serializer.is_valid()
        self.assertIn("body", serializer.errors)


class DiffProposalCreateSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        cls.user = cls.meeting.participants.create(username="participant")
        cls.meeting.add_roles(cls.user, ROLE_PROPOSER)
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(
            state="ongoing", title="Ongoing"
        )
        cls.text_doc: TextDocument = cls.ai.text_documents.create(
            body="I am the eggman\nI am the walrus"
        )
        cls.para: TextParagraph = cls.text_doc.text_paragraphs.first()

    @property
    def _cut(self):
        from voteit.proposal.rest_api.serializers import DiffProposalCreateSerializer

        return DiffProposalCreateSerializer

    def _mk_request(self):
        request = RequestFactory().get("/")
        request.user = self.user
        return request

    def test_create(self):
        body = "I am the eggman\nI am a very small animal"
        request = self._mk_request()
        serializer = self._cut(
            data={
                "body": body,
                "paragraph": self.para.pk,
                "agenda_item": self.ai.pk,
            },
            context={"request": request},
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        instance: DiffProposal = serializer.save()
        self.assertEqual(instance.body, body)

    def test_create_without_difference(self):
        body = "I am the eggman\nI am the walrus"
        request = self._mk_request()
        serializer = self._cut(
            data={
                "body": body,
                "paragraph": self.para.pk,
                "agenda_item": self.ai.pk,
            },
            context={"request": request},
        )
        serializer.is_valid()
        self.assertIn("body", serializer.errors)


class TextDocumentSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
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

    def test_modify(self):
        serializer = self._cut(self.text_doc, data=dict(base_tag="hi"))
        serializer.is_valid()
        self.assertFalse(serializer.errors)

    def test_modify_other(self):
        new_text_doc = self.ai.text_documents.create(
            body="I am the eggman\n\nI am the walrus", base_tag="hello"
        )
        serializer = self._cut(new_text_doc, data=dict(base_tag="hi"))
        serializer.is_valid()
        self.assertIn("base_tag", serializer.errors)


class CreateTextDocumentSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.user = cls.meeting.participants.get(username="moderator")
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(
            state="ongoing", title="Ongoing"
        )
        cls.text_doc: TextDocument = cls.ai.text_documents.create(
            body="I am the eggman\n\nI am the walrus", base_tag="hi"
        )

    @property
    def _cut(self):
        from voteit.proposal.rest_api.serializers import CreateTextDocumentSerializer

        return CreateTextDocumentSerializer

    def _mk_request(self):
        request = RequestFactory().get("/")
        request.user = self.user
        return request

    def test_create(self):
        serializer = self._cut(
            data={"agenda_item": self.ai.pk, "base_tag": "hej", "body": "Hello"},
            context={"request": self._mk_request()},
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        instance = serializer.create(serializer.validated_data)

    def test_create_duplicate(self):
        serializer = self._cut(
            data={"agenda_item": self.ai.pk, "base_tag": "hi", "body": "Hello"},
            context={"request": self._mk_request()},
        )
        serializer.is_valid()
        self.assertIn("base_tag", serializer.errors)

    def test_base_tag_sluggified(self):
        request = self._mk_request()
        serializer = self._cut(
            data={
                "agenda_item": self.ai.pk,
                "base_tag": "Hur mår du?",
                "body": "Hello",
            },
            context={"request": request},
        )
        serializer.is_valid()
        self.assertEqual("hur-mar-du", serializer.data["base_tag"])
