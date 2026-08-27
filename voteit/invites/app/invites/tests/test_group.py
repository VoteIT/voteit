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
        # A very unrelated invite
        cls.unrelated_inv = cls.meeting.invites.create(
            user_data={"email": "hello@world.com"}
        )
        # Groups
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
            "The following groupids doesn't exist: sabreclub", str(cm.exception)
        )

    def test_annotate(self):
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        annotations_formatted = list(self.registry.format_effect_rows(columns, rows))
        invites_qs = self.meeting.invites.all()
        result = self._cut.annotate(
            invites_qs=invites_qs,
            columns=columns,
            annotations_formatted=annotations_formatted,
            meeting=self.meeting,
            registry=self.registry,
        )
        data = result.dict()
        self.assertEqual(
            {self.inv_vader.pk, self.inv_luke.pk, self.inv_din.pk},
            set(data.pop("newly_annotated_invites")),
        )
        self.assertEqual(
            {
                "added": 5,
                "changed": 0,
                "existed": 0,
                "name": self._cut.name,
                "msg": None,
                "curr": None,
                "total": None,
            },
            data,
        )

    def _annotate(self, columns, rows):
        return self._cut.annotate(
            invites_qs=self.meeting.invites.all(),
            columns=columns,
            annotations_formatted=list(self.registry.format_effect_rows(columns, rows)),
            meeting=self.meeting,
            registry=self.registry,
        )

    def test_annotate_duplicate_row(self):
        """
        The same row twice must not reach the upsert twice — Postgres rejects a
        statement that touches the same row a second time — and must be counted
        once.
        """
        columns = ["email", "group", "grouprole"]
        rows = [
            ["vader@betahaus.net", "sw", "sith"],
            ["vader@betahaus.net", "sw", "sith"],
        ]
        result = self._annotate(columns, rows)
        self.assertEqual(1, result.added)
        self.assertEqual(0, result.changed)
        self.assertEqual(0, result.existed)
        annotation = self.inv_vader.group_annotations.get()
        self.assertEqual(self.group_sw, annotation.meeting_group)
        self.assertEqual(self.role_sith, annotation.group_role)

    def test_annotate_same_group_twice_with_different_role_last_wins(self):
        """
        Same person and group on two rows with different grouproles: the last row wins.

        This is the adapter-level fallback only. Every entry point runs
        registry.check_conflicting_annotations first, which rejects such rows --
        see the tests in rest_api/tests/.
        """
        columns = ["email", "group", "grouprole"]
        rows = [
            ["vader@betahaus.net", "sw", "sith"],
            ["vader@betahaus.net", "sw", "jedi"],
        ]
        result = self._annotate(columns, rows)
        self.assertEqual(1, result.added)
        annotation = self.inv_vader.group_annotations.get()
        self.assertEqual(self.role_jedi, annotation.group_role)

    def test_annotate_duplicate_row_for_accepted_invite(self):
        """The already-accepted branch writes one membership and counts it once."""
        self.inv_vader.accept(self.vader)
        self.inv_vader.save()
        columns = ["email", "group", "grouprole"]
        rows = [
            ["vader@betahaus.net", "sw", "sith"],
            ["vader@betahaus.net", "sw", "sith"],
        ]
        result = self._annotate(columns, rows)
        self.assertEqual(1, result.added)
        self.assertEqual(0, result.changed)
        self.assertEqual(0, result.existed)
        membership = self.group_sw.memberships.get(user=self.vader)
        self.assertEqual(self.role_sith, membership.role)

    def test_annotate_duplicate_row_different_groups_still_both_annotated(self):
        """Collapsing duplicates must not collapse distinct groups."""
        columns = ["email", "group"]
        rows = [
            ["vader@betahaus.net", "sw"],
            ["vader@betahaus.net", "sabreclub"],
            ["vader@betahaus.net", "sw"],
        ]
        result = self._annotate(columns, rows)
        self.assertEqual(2, result.added)
        self.assertEqual(
            {self.group_sw, self.group_sabreclub},
            {x.meeting_group for x in self.inv_vader.group_annotations.all()},
        )

    def test_annotate_some_existed(self):
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        annotations_formatted = list(self.registry.format_effect_rows(columns, rows))
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
        data = result.dict()
        newly_annotated_invites = set(data.pop("newly_annotated_invites"))
        self.assertEqual(
            {
                self.inv_vader.pk,
                self.inv_luke.pk,
            },
            newly_annotated_invites,
        )
        self.assertEqual(
            {
                "added": 2,
                "changed": 0,
                "existed": 3,
                "curr": None,
                "total": None,
                "name": self._cut.name,
                "msg": None,
            },
            data,
        )

    def test_annotate_some_existed_with_wrong_role(self):
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        annotations_formatted = list(self.registry.format_effect_rows(columns, rows))
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
        data = result.dict()
        newly_annotated_invites = set(data.pop("newly_annotated_invites"))
        self.assertEqual(
            {
                self.inv_vader.pk,
                self.inv_luke.pk,
            },
            newly_annotated_invites,
        )
        self.assertEqual(
            {
                "added": 2,
                "changed": 0,
                "existed": 3,
                "name": self._cut.name,
                "msg": None,
                "curr": None,
                "total": None,
            },
            data,
        )

    def test_annotate_mixed(self):
        self.inv_vader.user_data["swedish_ssn"] = "121212-1212"
        self.inv_vader.save()
        columns, rows = get_unvalidated_fixture_content("mixed_and_group.csv")
        annotations_formatted = list(self.registry.format_effect_rows(columns, rows))
        invites_qs = self.meeting.invites.all()
        result = self._cut.annotate(
            invites_qs=invites_qs,
            columns=columns,
            annotations_formatted=annotations_formatted,
            meeting=self.meeting,
            registry=self.registry,
        )
        self.assertEqual(5, result.added)

    def test_annotate_some_used_one_used_wrong_state(self):
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        annotations_formatted = list(self.registry.format_effect_rows(columns, rows))
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
                "curr": None,
                "total": None,
                "newly_annotated_invites": [],
            },
            result.dict(),
        )

    def test_prep_invites_qs_for_subscribe(self):
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        annotations_formatted = list(self.registry.format_effect_rows(columns, rows))
        invites_qs = self.meeting.invites.all()
        self._cut.annotate(
            invites_qs=invites_qs,
            columns=columns,
            annotations_formatted=annotations_formatted,
            meeting=self.meeting,
            registry=self.registry,
        )
        annotated_invites_qs = self._cut.prep_invites_qs_for_subscribe(invites_qs)
        self.assertEqual(
            [True, True, True, False],
            [
                self._cut(x).has_annotations()
                for x in annotated_invites_qs.order_by("pk")
            ],
        )

    def test_get_annotations(self):
        columns, rows = get_unvalidated_fixture_content("grouprole.csv")
        annotations_formatted = list(self.registry.format_effect_rows(columns, rows))
        invites_qs = self.meeting.invites.all()
        self._cut.annotate(
            invites_qs=invites_qs,
            columns=columns,
            annotations_formatted=annotations_formatted,
            meeting=self.meeting,
            registry=self.registry,
        )
        unrelated = self._cut(self.unrelated_inv)
        self.assertEqual([], list(unrelated.get_annotations()))
        luke = self._cut(self.inv_luke)
        self.assertEqual(
            [
                {"meeting_group": self.group_sw.pk, "role": self.role_jedi.pk},
                {"meeting_group": self.group_sabreclub.pk, "role": None},
            ],
            list(luke.get_annotations()),
        )

    def test_clear(self):
        qs = self._cut.clear(self.meeting)
        self.assertEqual(0, qs.count())
        self.inv_luke.group_annotations.create(meeting_group=self.group_sabreclub)
        qs = self._cut.clear(self.meeting)
        self.assertEqual({self.inv_luke}, set(qs))
