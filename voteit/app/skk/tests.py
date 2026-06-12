from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.active.components import ActiveUsersComponent
from voteit.app.skk.er import DELEGAT
from voteit.app.skk.er import DELEGAT_FULLMAKT
from voteit.app.skk.er import SUPPLEANT
from voteit.meeting.dialects import dialect_registry
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

User = get_user_model()


class SKKFumERPTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        handler = dialect_registry.get_merged_handler("skk_kennelfum")
        handler.install(cls.meeting)
        cls.role_fullmakt = cls.meeting.group_roles.get(role_id=DELEGAT_FULLMAKT)
        cls.role_delegat = cls.meeting.group_roles.get(role_id=DELEGAT)
        cls.role_suppleant = cls.meeting.group_roles.get(role_id=SUPPLEANT)
        cls.dobbermans: MeetingGroup = cls.meeting.groups.create(
            title="Dobbermans", votes=6
        )
        cls.user_a = cls.meeting.participants.create(username="a")
        cls.user_b = cls.meeting.participants.create(username="b")
        cls.user_c = cls.meeting.participants.create(username="c")
        cls.mem_a = cls.dobbermans.memberships.create(
            user=cls.user_a, role=cls.role_fullmakt
        )
        cls.mem_b = cls.dobbermans.memberships.create(
            user=cls.user_b, role=cls.role_delegat
        )
        cls.mem_c = cls.dobbermans.memberships.create(
            user=cls.user_c, role=cls.role_suppleant
        )

    @property
    def _cut(self):
        from voteit.app.skk.er import SKKFum

        return SKKFum

    def _mk_one(self):
        return self._cut(self.meeting)

    def test_too_many_votes(self):
        self.dobbermans.votes = 10
        self.dobbermans.save()
        erp = self._mk_one()
        self.assertEqual(
            {self.user_a.pk: 2, self.user_b.pk: 2, self.user_c.pk: 2}, erp.get_voters()
        )

    def test_potential_voters_respected(self):
        self.meeting.remove_roles(self.user_a, ROLE_POTENTIAL_VOTER)
        erp = self._mk_one()
        self.assertEqual({self.user_b.pk: 2, self.user_c.pk: 2}, erp.get_voters())

    def test_order_of_entry_5(self):
        self.dobbermans.votes = 5
        self.dobbermans.save()
        erp = self._mk_one()
        self.assertEqual(
            {self.user_a.pk: 2, self.user_b.pk: 2, self.user_c.pk: 1}, erp.get_voters()
        )

    def test_order_of_entry_4(self):
        self.dobbermans.votes = 4
        self.dobbermans.save()
        erp = self._mk_one()
        self.assertEqual(
            {
                self.user_a.pk: 2,
                self.user_b.pk: 2,
            },
            erp.get_voters(),
        )

    def test_order_of_entry_3(self):
        self.dobbermans.votes = 3
        self.dobbermans.save()
        erp = self._mk_one()
        self.assertEqual({self.user_a.pk: 2, self.user_b.pk: 1}, erp.get_voters())

    def test_order_of_entry_2(self):
        self.dobbermans.votes = 2
        self.dobbermans.save()
        erp = self._mk_one()
        self.assertEqual({self.user_a.pk: 1, self.user_b.pk: 1}, erp.get_voters())

    def test_order_of_entry_1(self):
        self.dobbermans.votes = 1
        self.dobbermans.save()
        erp = self._mk_one()
        self.assertEqual({self.user_a.pk: 1}, erp.get_voters())

    def test_active_respected(self):
        self.meeting.components.create(
            component_name=ActiveUsersComponent.name, enabled=True
        )
        self.meeting.active_users.create(user=self.user_a)
        erp = self._mk_one()
        self.assertEqual({self.user_a.pk: 2}, erp.get_voters())
