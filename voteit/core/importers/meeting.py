import os

from django.core import serializers
from django.db import DEFAULT_DB_ALIAS
from django.db import DatabaseError
from django.db import IntegrityError
from django.db import router
from django.db import transaction
from django.utils.timezone import now

from voteit.core.utils import get_content_registry
from voteit.core.utils import get_model_shortname


# These are remaps that target attributes with the same name as the content type, so we don't need to specify them.
# For instance proposal objects always have agenda_item linking to one agenda_item.
DEFAULT_REMAPS = {
    "meeting",
    "agenda_item",
    "speaker_system",
    "meeting_group",
}


class MeetingImport:

    """
    Import configuration

    remap_relations
        A dict with relations to update where key is the model shortname and the value is the attribute on this model.
        For instance agenda items need: remap_relations = {'meeting': 'meeting'}
    """

    def __init__(
        self,
        remap_relations: dict = None,
    ):
        if remap_relations:
            reg = get_content_registry()
            assert isinstance(remap_relations, dict)
            for k in remap_relations:
                assert k in reg, f"No content type with key: {k}"
            self.remap_relations = remap_relations
        else:
            self.remap_relations = {}
        for default_remap in DEFAULT_REMAPS:
            self.remap_relations.setdefault(default_remap, default_remap)


class MeetingImporter:
    def __init__(self, using=DEFAULT_DB_ALIAS, filename=None, stream=None):
        self.using = using
        # self.models = set()
        self.objs_with_deferred_fields = []
        if bool(filename) == bool(stream):
            raise ValueError("specify either stream or filename")
        if filename:
            if not os.path.isfile(filename):
                ValueError(f"{filename} is not an existing file")
            stream = open(filename, "r")
        self.stream = stream
        # Dicts with old pk as key
        self.objects_to_handle = {}
        # Importer helpers
        self.importers = {}
        for (name, model) in get_content_registry().items():
            if importers := getattr(model, "importers", None):
                if "meeting" in importers:
                    self.importers[name] = MeetingImport(**importers["meeting"])

    def run(self):
        # We need to muck about with all objects so keeping them in memory (or later in a temp file) is required :/
        all_objects = list(
            serializers.deserialize(
                "yaml",
                self.stream,
                using=self.using,
                handle_forward_references=True,
            )
        )
        deserialized_meeting = None

        # Walk
        for deserialized in all_objects:
            name = get_model_shortname(deserialized.object)
            if name == "meeting":
                if name in self.objects_to_handle:
                    raise ValueError("Multiple meetings found in file")
                deserialized_meeting = deserialized
            items = self.objects_to_handle.setdefault(name, {})
            items[deserialized.object.pk] = deserialized
        if deserialized_meeting is None:
            raise ValueError("No meeting found")

        import_order = ["meeting", "agenda_item", "speaker_system", "meeting_group"]
        # FIXME: Figure out ordering from relations that need to be replaced instead.

        with transaction.atomic():
            self.update_special_fields(deserialized_meeting.object)
            # FIXME: Set title?
            deserialized_meeting.object.title = (
                deserialized_meeting.object.title + f"-copy-{now().date()}"
            )
            self.save_obj(deserialized_meeting)
            [
                import_order.append(x)
                for x in self.objects_to_handle
                if x not in import_order
            ]
            import_order.pop(0)  # Meeting already handled
            for name in import_order:
                items = self.objects_to_handle[name]
                for deserialized in items.values():
                    self.update_special_fields(deserialized.object)
                    self.save_obj(deserialized)
            # And the m2ms
            for deserialized in self.objs_with_deferred_fields:
                deserialized.save_deferred_fields(using=self.using)
        self.stream.close()

    def update_special_fields(self, obj):
        field_names = [x.name for x in obj._meta.local_concrete_fields]
        name = get_model_shortname(obj)
        importer = self.importers[name]
        for model_name, relation_attr_name in importer.remap_relations.items():
            if relation_attr_name in field_names:
                curr_val = getattr(obj, relation_attr_name)
                # ObjectNotFound?
                if curr_val:
                    setattr(
                        obj,
                        relation_attr_name,
                        self.objects_to_handle[model_name][curr_val.pk].object,
                    )
        # FIXME: This might not be a good idea all of the time?
        if "created" in field_names:
            obj.created = now()
        if "modified" in field_names:
            obj.modified = now()
        # And clear pk
        obj.pk = None

    def save_obj(self, obj):
        saved = False
        if router.allow_migrate_model(self.using, obj.object.__class__):
            saved = True
            # FIXME: This is probably not needed, from the loaddata-script
            # self.models.add(obj.object.__class__)
            try:
                obj.save(using=self.using)
            # psycopg2 raises ValueError if data contains NUL chars.
            except (DatabaseError, IntegrityError, ValueError) as e:
                e.args = (
                    "Could not load %(object_label)s(pk=%(pk)s): %(error_msg)s"
                    % {
                        "object_label": obj.object._meta.label,
                        "pk": obj.object.pk,
                        "error_msg": e,
                    },
                )
                raise
        if obj.deferred_fields:
            self.objs_with_deferred_fields.append(obj)
        return saved
