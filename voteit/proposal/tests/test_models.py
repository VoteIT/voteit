from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import RestrictedError
from django.test import TestCase
from voteit.meeting.models import Meeting

User = get_user_model()


class ProposalTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.ai = cls.meeting.agenda_items.create()
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.group = cls.meeting.groups.create()

    @property
    def _cut(self):
        from voteit.proposal.models import Proposal

        return Proposal

    def _mk_one(self, **kw):
        return self._cut.objects.create(**kw)

    def test_author_cant_be_deleted(self):
        user = User.objects.create(username="hi")
        self._mk_one(author=user)
        with self.assertRaises(RestrictedError):
            user.delete()

    def test_prop_id_in_tags(self):
        prop = self._mk_one(prop_id="hello")
        self.assertIn("hello", prop.tags)

    def test_prop_id_unique_to_agenda(self):
        one = self._mk_one(prop_id="hello", agenda_item=self.ai)
        self.assertEqual("hello", one.prop_id)
        with self.assertRaises(IntegrityError):
            self._mk_one(prop_id="hello", agenda_item=self.ai)

    def test_default_prop_id_based_on_userid(self):
        user = User.objects.create(username="not-used", userid="hi")
        user2 = User.objects.create(username="for-this", userid="hello")
        prop = self._mk_one(agenda_item=self.ai, author=user)
        self.assertEqual("hi-1", prop.prop_id)
        prop = self._mk_one(agenda_item=self.ai, author=user)
        self.assertEqual("hi-2", prop.prop_id)
        prop = self._mk_one(agenda_item=self.ai, author=user2)
        self.assertEqual("hello-1", prop.prop_id)

    def test_as_group_restrictions(self):
        prop = self._mk_one(author=self.participant, as_group=True)
        self.assertFalse(prop.as_group)
        prop = self._mk_one(
            author=self.participant, meeting_group=self.group, as_group=True
        )
        self.assertTrue(prop.as_group)

    # def test_userid_based_prop_id_changed_with_author(self):
    #     prop = self._mk_one(agenda_item=self.ai, author=self.moderator)
    #     self.assertEqual("moderator-1", prop.prop_id)
    #     self.assertEqual(["moderator-1"], prop.tags)
    #     prop.author = self.participant
    #     self.assertEqual("participant-1", prop.prop_id)
    #     self.assertEqual(["participant-1"], prop.tags)
    #
    # def test_userid_based_prop_id_not_changed_with_author_if_used_elsewhere(self):
    #     pass


class DiffProposalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.agenda.models import AgendaItem
        from voteit.proposal.models import TextDocument
        from voteit.proposal.models import DiffProposal

        cls.meeting: Meeting = Meeting.objects.create()
        cls.ai: AgendaItem = cls.meeting.agenda_items.create()
        cls.text_doc: TextDocument = TextDocument.objects.create(
            body="Hello", base_tag="hi"
        )
        cls.para = cls.text_doc.text_paragraphs.first()
        cls.diff_prop: DiffProposal = cls.para.proposals.create(agenda_item=cls.ai)
        cls.prop = cls.ai.proposals.create()

    def test_manager_fetches_all_types_by_default(self):
        self.assertEqual(
            {self.diff_prop, self.prop},
            set(self.ai.proposals.all().select_subclasses()),
        )


TEXT = """
The bureaucracy is expanding to meet the needs of the expanding bureaucracy.

-- Oscar Wilde
"""


class TextDocumentTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.agenda.models import AgendaItem

        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.ai: AgendaItem = cls.meeting.agenda_items.create()

    def test_create_makes_paragraphs_too(self):
        obj = self.ai.text_documents.create(body=TEXT, base_tag="oscar")
        paras = list(obj.text_paragraphs.order_by("paragraph_id"))
        self.assertEqual(
            "The bureaucracy is expanding to meet the needs of the expanding bureaucracy.",
            paras[0].body,
        )
        self.assertEqual(1, paras[0].paragraph_id)
        self.assertEqual("oscar-1", paras[0].tag)
        self.assertEqual(
            "-- Oscar Wilde",
            paras[1].body,
        )
        self.assertEqual(2, paras[1].paragraph_id)
        self.assertEqual("oscar-2", paras[1].tag)

    def test_new_body_detected(self):
        obj = self.ai.text_documents.create(body=TEXT, base_tag="oscar")
        obj.body = "new"
        obj.save()
        self.assertFalse(obj.should_refresh)
        para = obj.text_paragraphs.first()
        self.assertEqual("new", para.body)
