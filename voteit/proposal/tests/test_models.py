from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase


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
        from voteit.agenda.models import AgendaItem
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        ai = AgendaItem.objects.create(meeting=meeting)
        self._mk_one(prop_id="hello", agenda_item=ai)
        with self.assertRaises(IntegrityError):
            self._mk_one(prop_id="hello", agenda_item=ai)
