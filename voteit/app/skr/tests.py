import os
from collections import Counter

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from voteit.app.skr import KOMMUN_TAG
from voteit.app.skr import REGION_TAG
from voteit.app.testing import DIALECT_FIXTURES
from voteit.meeting.dialects import dialect_registry
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.exceptions import ElectoralRegisterError

User = get_user_model()
os.path.join(__file__)


@override_settings(MEETING_DIALECTS_DIR=DIALECT_FIXTURES)
class SKRAgarradERPTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(state="ongoing")
        handler = dialect_registry.get_merged_handler("skr_agarrad")
        handler.install(cls.meeting)
        cls.mimmi = cls.meeting.participants.create(username="mimmi")
        cls.robin = cls.meeting.participants.create(username="robin")
        cls.anna = cls.meeting.participants.create(username="anna")
        cls.teresa = cls.meeting.participants.create(username="teresa")
        cls.users = cls.mimmi, cls.robin, cls.anna, cls.teresa
        for user in cls.users:
            cls.meeting.add_roles(user, ROLE_PARTICIPANT, ROLE_POTENTIAL_VOTER)
            cls.meeting.active_users.create(user=user)
        cls.grp_gotland = cls.meeting.groups.get(groupid="0980")
        cls.grp_gotland.members.add(cls.mimmi)
        cls.grp_stockholm = cls.meeting.groups.get(groupid="0180")
        cls.grp_stockholm.members.add(cls.robin)
        cls.grp_goteborg = cls.meeting.groups.get(groupid="1480")
        cls.grp_goteborg.members.add(cls.anna)
        cls.grp_skr = cls.meeting.groups.get(groupid="skr")
        cls.grp_skr.members.add(cls.teresa)
        # Poll fixtures
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop = cls.ai.proposals.create()
        cls.poll = cls.meeting.polls.create(method_name="simple")
        cls.poll.proposals.add(cls.prop)

    @property
    def _cut(self):
        from voteit.app.skr.er import SKRAgarradERP

        return SKRAgarradERP

    def _mk_one(self):
        return self._cut(self.meeting)

    def test_voters(self):
        erp = self._mk_one()
        self.assertEqual(
            {self.robin.pk: 1, self.teresa.pk: 2, self.anna.pk: 1, self.mimmi.pk: 1},
            erp.get_voters(),
        )

    def test_active_respected(self):
        self.meeting.active_users.filter(user=self.robin).delete()
        erp = self._mk_one()
        self.assertEqual(
            {self.teresa.pk: 1, self.anna.pk: 1, self.mimmi.pk: 1},
            erp.get_voters(),
        )

    def test_delegate_to_gotland(self):
        self.meeting.active_users.filter(user=self.robin).delete()
        self.meeting.active_users.filter(user=self.anna).delete()
        self.grp_stockholm.delegate_to = self.grp_gotland
        self.grp_stockholm.save()
        self.grp_goteborg.delegate_to = self.grp_gotland
        self.grp_goteborg.save()
        erp = self._mk_one()
        self.assertEqual(
            {self.teresa.pk: 2, self.mimmi.pk: 3},
            erp.get_voters(),
        )

    def test_delegate_to_skr(self):
        self.meeting.active_users.filter(user=self.robin).delete()
        self.meeting.active_users.filter(user=self.anna).delete()
        self.grp_stockholm.delegate_to = self.grp_skr
        self.grp_stockholm.save()
        self.grp_goteborg.delegate_to = self.grp_skr
        self.grp_goteborg.save()
        erp = self._mk_one()
        self.assertEqual(
            {self.teresa.pk: 4, self.mimmi.pk: 1},
            erp.get_voters(),
        )

    def test_skr_user_in_other_group(self):
        self.grp_stockholm.members.remove(self.robin)
        self.grp_stockholm.members.add(self.teresa)
        erp = self._mk_one()
        with self.assertRaises(ElectoralRegisterError):
            erp.get_voters()

    def test_kommun_region_intersection(self):
        self.grp_stockholm.tags = [REGION_TAG, KOMMUN_TAG]
        self.grp_stockholm.save()
        erp = self._mk_one()
        with self.assertRaises(ElectoralRegisterError):
            erp.get_voters()

    def test_categorize_vote_power(self):
        self.poll.ongoing(force=True)
        self.poll.save()
        for user in self.users:
            self.poll.votes.create(user=user, vote="yes")
        erp = self._mk_one()
        result = erp.categorize_vote_power(self.poll)
        self.assertEqual({"yes": Counter({"kommun": 3, "skr": 2})}, result)
