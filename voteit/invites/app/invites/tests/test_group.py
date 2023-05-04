from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.invites.testing import get_unvalidated_fixture_content
from voteit.invites.utils import get_invite_adapter_registry
from voteit.meeting.models import Meeting
from voteit.invites.models import MeetingInvite
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.organisation.models import Organisation

User = get_user_model()


class GroupAnnotationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org: Organisation = Organisation.objects.create()
        cls.meeting: Meeting = cls.org.meetings.create()
        cls.din = cls.org.users.create(username="din", email="vader@betahaus.net")
        cls.luke = cls.org.users.create(username="luke", email="luke@betahaus.net")
        cls.vader = cls.org.users.create(username="vader", email="vader@betahaus.net")
        # Invite fixture
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        cls.registry = get_invite_adapter_registry()
        invite_data = list(cls.registry.build_ud_query_seq(columns, rows))
        cls.meeting.invites.create_or_update_mixed(
            data=invite_data, roles=[ROLE_PARTICIPANT], meeting=cls.meeting
        )
        cls.inv_din: MeetingInvite = MeetingInvite.objects.get(
            user_data={"email": "din@betahaus.net"}
        )
        cls.inv_vader: MeetingInvite = MeetingInvite.objects.get(
            user_data={"email": "vader@betahaus.net"}
        )
        cls.inv_luke: MeetingInvite = MeetingInvite.objects.get(
            user_data={"email": "luke@betahaus.net"}
        )
        cls.group_sabreclub = cls.meeting.groups.create(groupid="sabreclub")
        cls.group_sw = cls.meeting.groups.create(groupid="sw")
        cls.role_sith = cls.meeting.group_roles.create(role_id="sith")
        cls.role_jedi = cls.meeting.group_roles.create(role_id="jedi")

    @property
    def _cut(self):
        from voteit.invites.app.invites.group import InviteGroup

        return InviteGroup

    def test_validate(self):
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        self.assertIsNone(
            self._cut.validate(columns=columns, rows=rows, meeting=self.meeting)
        )

    def test_validate_groupid_missing(self):
        self.group_sabreclub.delete()
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        with self.assertRaises(ValueError) as cm:
            self._cut.validate(columns=columns, rows=rows, meeting=self.meeting)
        self.assertEqual(
            "The following groupids don't exist: sabreclub", str(cm.exception)
        )

    def test_annotate(self):
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        annotations_formatted = list(
            self.registry.format_for_annotations(columns, rows)
        )
        invites_qs = self.meeting.invites.all()
        result = self._cut.annotate(
            invites_qs=invites_qs,
            columns=columns,
            annotations_formatted=annotations_formatted,
            meeting=self.meeting,
            registry=self.registry,
        )
        self.assertEqual(
            {
                "added": 5,
                "changed": 0,
                "existed": 0,
                "name": self._cut.name,
                "msg": None,
            },
            result.dict(),
        )

    def test_annotate_some_existed(self):
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        annotations_formatted = list(
            self.registry.format_for_annotations(columns, rows)
        )
        invites_qs = self.meeting.invites.all()
        self._cut.annotate(
            invites_qs=invites_qs,
            columns=columns,
            annotations_formatted=annotations_formatted,
            meeting=self.meeting,
            registry=self.registry,
        )
        self.group_sabreclub.invite_annotations.all().delete()
        result = self._cut.annotate(
            invites_qs=invites_qs,
            columns=columns,
            annotations_formatted=annotations_formatted,
            meeting=self.meeting,
            registry=self.registry,
        )
        self.assertEqual(
            {
                "added": 2,
                "changed": 0,
                "existed": 3,
                "name": self._cut.name,
                "msg": None,
            },
            result.dict(),
        )

    def test_annotate_some_existed_with_wrong_role(self):
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        annotations_formatted = list(
            self.registry.format_for_annotations(columns, rows)
        )
        invites_qs = self.meeting.invites.all()
        self._cut.annotate(
            invites_qs=invites_qs,
            columns=columns,
            annotations_formatted=annotations_formatted,
            meeting=self.meeting,
            registry=self.registry,
        )
        self.group_sabreclub.invite_annotations.all().delete()
        result = self._cut.annotate(
            invites_qs=invites_qs,
            columns=columns,
            annotations_formatted=annotations_formatted,
            meeting=self.meeting,
            registry=self.registry,
        )
        self.assertEqual(
            {
                "added": 2,
                "changed": 0,
                "existed": 3,
                "name": self._cut.name,
                "msg": None,
            },
            result.dict(),
        )

    def test_annotate_some_used_one_used_wrong_state(self):
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        annotations_formatted = list(
            self.registry.format_for_annotations(columns, rows)
        )
        self._cut.annotate(
            invites_qs=self.meeting.invites.all(),
            columns=columns,
            annotations_formatted=annotations_formatted,
            meeting=self.meeting,
            registry=self.registry,
        )
        self.inv_luke.accept(self.luke)
        self.inv_luke.save()
        self.inv_vader.accept(self.vader)
        self.inv_vader.save()
        gm = self.group_sw.memberships.filter(user=self.vader).first()
        gm.role = None
        gm.save()
        result = self._cut.annotate(
            invites_qs=self.meeting.invites.all(),
            columns=columns,
            annotations_formatted=annotations_formatted,
            meeting=self.meeting,
            registry=self.registry,
        )
        self.assertEqual(
            {
                "added": 0,
                "changed": 1,
                "existed": 4,
                "name": self._cut.name,
                "msg": None,
            },
            result.dict(),
        )
