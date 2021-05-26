from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase
from voteit.meeting.models import Meeting

User = get_user_model()


class ProposalTests(TestCase):
    @property
    def _cut(self):
        from voteit.proposal.models import Proposal

        return Proposal

    def _mk_one(self, **kw):
        return self._cut.objects.create(**kw)

    def test_author_cant_be_deleted(self):
        user = User.objects.create(username="hi")
        self._mk_one(author=user)
        with self.assertRaises(ProtectedError):
            user.delete()

    def test_prop_id_in_tags(self):
        prop = self._mk_one(prop_id="hello")
        self.assertIn("hello", prop.tags)

    def test_prop_id_unique_to_agenda(self):
        meeting = Meeting.objects.create()
        ai = meeting.agenda_items.create()
        self._mk_one(prop_id="hello", agenda_item=ai)
        with self.assertRaises(IntegrityError):
            self._mk_one(prop_id="hello", agenda_item=ai)

    def test_default_prop_id_based_on_userid(self):
        user = User.objects.create(username="not-used", userid="hi")
        user2 = User.objects.create(username="for-this", userid="hello")
        meeting = Meeting.objects.create()
        ai = meeting.agenda_items.create()
        prop = self._mk_one(agenda_item=ai, author=user)
        self.assertEqual("hi-1", prop.prop_id)
        prop = self._mk_one(agenda_item=ai, author=user)
        self.assertEqual("hi-2", prop.prop_id)
        prop = self._mk_one(agenda_item=ai, author=user2)
        self.assertEqual("hello-1", prop.prop_id)
