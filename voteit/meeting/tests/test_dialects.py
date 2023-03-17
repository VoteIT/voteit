from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from pydantic import ValidationError

from voteit.components.app.components.message import FlashMessage
from voteit.core.workflows import EnabledWf
from voteit.meeting.exceptions import DialectError
from voteit.meeting.models import Meeting
from voteit.meeting.tests.fixtures import DIALECT_FIXTURES

User = get_user_model()


dialect_named_test = {
    "title": "Test",
    "name": "test",
    "roles": [
        {
            "title": "Supervisor",
            "role_id": "supervisor",
            "roles": ["discusser", "proposer"],
        }
    ],
    "groups": [{"title": "Board", "groupid": "board"}],
    "er_policy_name": "auto_before_poll",
    "group_votes_active": True,
    "group_roles_active": True,
}
dialect_with_component = {**dialect_named_test}
dialect_with_component.update(
    {
        "block_components": ["repeated_irv"],
        "configure_components": [
            {"name": FlashMessage.name, "settings": {"msg": "Hello!"}}
        ],
    }
)
dialect_minimal = {"title": "Mini", "name": "mini"}
dialect_minimal_requires_test = {"title": "Req", "name": "req", "requires": ["test"]}


class DialectHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()

    @property
    def _cut(self):
        from voteit.meeting.dialects import DialectHandler

        return DialectHandler

    def test_load_with_bad_data(self):
        with self.assertRaises(ValidationError):
            self._cut.load_from_dict({})

    def test_install(self):
        handler = self._cut.load_from_dict(dialect_named_test)
        handler.install(self.meeting)
        self.assertEqual("test", self.meeting.installed_dialects)
        self.assertEqual("auto_before_poll", self.meeting.er_policy_name)
        self.assertTrue(self.meeting.group_votes_active)
        self.assertTrue(self.meeting.group_roles_active)
        group_role = self.meeting.group_roles.filter(role_id="supervisor").first()
        self.assertIsNotNone(group_role)
        self.assertEqual("Supervisor", group_role.title)
        group = self.meeting.groups.filter(groupid="board").first()
        self.assertIsNotNone(group)
        self.assertEqual("Board", group.title)

    def test_install_adjusts_groups_and_roles(self):
        group_role = self.meeting.group_roles.create(
            title="Jeff", role_id="supervisor", roles=["discusser"]
        )
        group = self.meeting.groups.create(title="Jane", groupid="board")
        handler = self._cut.load_from_dict(dialect_named_test)
        handler.install(self.meeting)
        group_role.refresh_from_db()
        group.refresh_from_db()
        self.assertEqual("Supervisor", group_role.title)
        self.assertEqual(["discusser", "proposer"], group_role.roles)
        self.assertEqual("Board", group.title)

    def test_remove(self):
        handler = self._cut.load_from_dict(dialect_named_test)
        handler.install(self.meeting)
        self.assertEqual("test", self.meeting.installed_dialects)
        handler.remove(self.meeting)
        self.assertIsNone(self.meeting.installed_dialects)
        self.assertIsNone(self.meeting.group_roles.filter(role_id="supervisor").first())
        self.assertIsNone(self.meeting.groups.filter(groupid="board").first())
        self.assertIsNone(self.meeting.er_policy_name)
        self.assertFalse(self.meeting.group_votes_active)
        self.assertFalse(self.meeting.group_roles_active)

    def test_duplicate_install(self):
        handler = self._cut.load_from_dict(dialect_named_test)
        self.meeting.installed_dialects = handler.data.name
        with self.assertRaises(DialectError):
            handler.install(self.meeting)

    def test_remove_with_none_installed(self):
        handler = self._cut.load_from_dict(dialect_named_test)
        with self.assertRaises(DialectError):
            handler.remove(self.meeting)

    def test_install_requires_other(self):
        handler = self._cut.load_from_dict(dialect_named_test)
        handler.install(self.meeting)
        handler_req = self._cut.load_from_dict(dialect_minimal_requires_test)
        handler_req.install(self.meeting)
        self.assertEqual("test,req", self.meeting.installed_dialects)

    def test_install_missing_required(self):
        handler = self._cut.load_from_dict(dialect_minimal_requires_test)
        with self.assertRaises(DialectError):
            handler.install(self.meeting)

    def test_uninstall_leaves_untouched_settings_intact(self):
        self.meeting.group_votes_active = True
        self.meeting.group_roles_active = True
        self.meeting.proposal_id_policy_name = "auto_before_poll"
        self.meeting.save()
        handler = self._cut.load_from_dict(dialect_minimal)
        handler.install(self.meeting)
        handler.remove(self.meeting)
        self.assertTrue(self.meeting.group_votes_active)
        self.assertTrue(self.meeting.group_roles_active)
        self.assertEqual("auto_before_poll", self.meeting.proposal_id_policy_name)

    def test_install_with_component(self):
        handler = self._cut.load_from_dict(dialect_with_component)
        handler.install(self.meeting)
        component = self.meeting.components.filter(
            component_name=FlashMessage.name
        ).first()
        self.assertEqual({"msg": "Hello!"}, component.settings_data)
        self.assertEqual(EnabledWf.ON, component.state)


@override_settings(MEETING_DIALECTS_DIR=DIALECT_FIXTURES)
class DialectRegistryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.dialects import DialectRegistry

        cls.registry = DialectRegistry()

    def test_get_installable(self):
        self.assertEqual(
            {"three": "Three", "main_subst": "Main/subst", "two": "Two!"},
            self.registry.get_installable(),
        )
        self.assertEqual(
            {"three": "Three", "main_subst": "Main/subst"},
            self.registry.get_installable(exclude={"two"}),
        )
        self.assertEqual(
            {
                "main_subst": "Main/subst",
                "one": "Hello",
                "three": "Three",
                "two": "Two!",
            },
            self.registry.get_installable(include={"one"}),
        )

    def test_get_merged_handler(self):
        handler = self.registry.get_merged_handler("two")
        self.assertEqual(
            {
                "description": "",
                "group_roles_active": True,
                "groups": [
                    {"groupid": "pirates"},
                    {"groupid": "swashbucklers"},
                    {"groupid": "shiphands"},
                ],
                "installable": True,
                "name": "two",
                "requires": ["one"],
                "title": "Two!",
                "view_components": {},
            },
            handler.data.dict(exclude_none=True, skip_defaults=True),
        )

    #
    # @override_settings(MEETING_DIALECTS_DIR=DIALECT_FIXTURES)
    # def test_install_fixture_with_component(self):
    #     main_subst
    #     handlers = get_merged_dialect_data(only="main_subst")
    #     handler = self._cut.load_from_dict(handlers["main_subst"])
    #     handler.install(self.meeting)
    #     component = self.meeting.components.filter(
    #         component_name=ActiveUsersComponent.name
    #     ).first()
    #     self.failUnless(component)
    #     self.assertEqual(EnabledWf.ON, component.state)


# class RecursiveLoadHandlersTests(TestCase):
#     @property
#     def _fut(self):
#         from voteit.meeting.utils import recursive_load_handlers
#
#         return recursive_load_handlers
#
#     @override_settings(MEETING_DIALECTS_DIR=DIALECT_FIXTURES)
#     def test_recursive(self):
#         result = self._fut("three")
#         self.assertEqual(["one", "two", "three"], [x.data.name for x in result])
#
#     @override_settings(MEETING_DIALECTS_DIR=BAD_DIALECT_FIXTURES)
#     def test_recursive_bad_req(self):
#         with self.assertRaises(DialectError):
#             self._fut("bad_req")
#
#     @override_settings(MEETING_DIALECTS_DIR=CYCLIC_DIALECT_FIXTURES)
#     def test_recursive_cyclic(self):
#         with self.assertRaises(DialectError):
#             self._fut("one")
