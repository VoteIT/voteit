from __future__ import annotations

import os
from abc import ABC
from abc import abstractmethod
from typing import Generator
from typing import TYPE_CHECKING

from django.core import serializers
from django.core.serializers.base import DeserializedObject
from django.db import DEFAULT_DB_ALIAS
from django.db import DatabaseError
from django.db import IntegrityError
from django.db import models
from django.db import router

from voteit.core.utils import get_content_registry
from voteit.core.utils import get_model_shortname

# These are remaps that target attributes with the same name as the content type, so we don't need to specify them.
# For instance proposal objects always have agenda_item linking to one agenda_item.
if TYPE_CHECKING:
    from voteit.poll.app.polls.combined_simple import CombinedSimplePollResult
    from voteit.poll.app.polls.dutt import DuttResultSchema
    from voteit.poll.app.polls.majority import MajorityPollResult
    from voteit.poll.app.polls.schulze import RepeatedSchulzeResult
    from voteit.poll.app.polls.schulze import SchulzePollResult
    from voteit.poll.app.polls.scottish_stv import STVResultSchema


DEFAULT_REMAPS = {
    "meeting",
    "agenda_item",
    "speaker_system",
    "speaker_list",
    "meeting_group",
    "organisation",
    "user",
    "poll",
    "text_document",
}


class BaseImport(ABC):
    """
    Import configuration

    remap_relations
        A dict with relations to update where key is the model shortname and the value is the attribute on this model.
        For instance agenda items need: remap_relations = {'meeting': 'meeting'}, which is default from DEFAULT_REMAPS.
    """

    default_remaps = DEFAULT_REMAPS

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique name for this importer type
        """

    settings_key = None  # Default to name

    def __init__(self, remap_relations: dict = None):
        self.remap_relations = {}
        # if isinstance(ignore, str):
        #     ignore = {ignore}
        # self.ignore = set(ignore)
        if remap_relations:
            reg = get_content_registry()
            assert isinstance(remap_relations, dict)
            for k, v in remap_relations.items():
                assert k in reg, f"No content type with key: {k}"
                attrs = self.remap_relations.setdefault(k, set())
                if isinstance(v, str):
                    attrs.add(v)
                else:
                    attrs.update(v)
        for remap in self.default_remaps:
            attrs = self.remap_relations.setdefault(remap, set())
            attrs.add(remap)


class BaseImporter(ABC):
    @property
    @abstractmethod
    def import_class(self) -> type[BaseImport]: ...

    def __init__(self, using=DEFAULT_DB_ALIAS, filename=None, stream=None, format=None):
        self.using = using
        self.objs_with_deferred_fields = []
        if bool(filename) == bool(stream):
            raise ValueError("specify either stream or filename")
        if filename:
            if not os.path.isfile(filename):
                ValueError(f"{filename} is not an existing file")
            stream = open(filename)
            if format is None:
                if filename.endswith("yaml") or filename.endswith("yml"):
                    format = "yaml"
                elif filename.endswith("json"):
                    format = "json"
        assert isinstance(format, str)
        self.format = format
        self.stream = stream
        # Dicts with old pk as key
        self.objects_to_handle = {}
        # Importer helpers
        self.importers = {}
        settings_key = getattr(self.import_class, "settings_key", None)
        if settings_key is None:
            settings_key = self.import_class.name
        assert isinstance(settings_key, str)
        for name, model in get_content_registry().items():
            if importers := getattr(model, "importers", None):
                if settings_key in importers:
                    try:
                        self.importers[name] = self.import_class(
                            **importers[settings_key]
                        )
                    except Exception as exc:
                        print(
                            f"Model: {model} - Importers settings: {importers[settings_key]}"
                        )
                        raise

    @abstractmethod
    def run(self, **kwargs): ...

    def get_remap_obj(self, shortname: str, curr_val: int) -> models.Model:
        assert isinstance(
            curr_val, int
        ), "field_name must point to the *_id field of the FK relation"
        remap_to = self.objects_to_handle[shortname][curr_val]
        if isinstance(remap_to, DeserializedObject):
            remap_to = remap_to.object
        assert isinstance(remap_to, models.Model)
        assert isinstance(remap_to.pk, int)
        return remap_to

    def add_obj_to_handle(self, obj: models.Model | DeserializedObject):
        if isinstance(obj, DeserializedObject):
            name = get_model_shortname(obj.object)
            pk = obj.object.pk
        elif isinstance(obj, models.Model):
            name = get_model_shortname(obj)
            pk = obj.pk
        else:
            raise ValueError(
                f"{obj} is not an instance of Django Model or a DeserializedObject"
            )
        assert pk
        items = self.objects_to_handle.setdefault(name, {})
        items[pk] = obj

    def load_objects(self) -> Generator[DeserializedObject]:
        return serializers.deserialize(
            self.format,
            self.stream,
            using=self.using,
            handle_forward_references=True,
        )

    def update_deferred(self):
        # And the m2ms
        for deserialized in self.objs_with_deferred_fields:
            deserialized.save_deferred_fields(using=self.using)

    def remap_fk_relation(self, obj, field_name, relation_model_name) -> int | None:
        """
        Returns int pk if relation was a pointer to superclass. In that case, use the value for pk.
        """
        id_name = f"{field_name}_id"
        curr_val = getattr(obj, id_name)
        # Forward pointers may have none as import value,
        # they should use the primary key of the object instead in that case
        is_pointer = False
        if id_name.endswith("_ptr_id"):
            is_pointer = True
            if curr_val is None:
                # Pretty lame check but whatever
                print("Remapped ptr")
                assert obj.pk is not None
                curr_val = obj.pk
        # In case curr_val was actually changed
        if curr_val is not None:
            remap_to = self.get_remap_obj(relation_model_name, curr_val)
            setattr(obj, field_name, remap_to)
            if is_pointer:
                return remap_to.pk

    def remap_schule_round(self, result: dict):
        new_pairs = []
        for pair in result.pairs:
            # [ [1,2], v]
            remapped = []
            for x in pair[0]:
                remapped.append(self.get_remap_obj("proposal", x).pk)
            new_pairs.append([remapped, pair[1]])
        result.pairs = new_pairs
        result.candidates = [
            self.get_remap_obj("proposal", x).pk for x in result.candidates
        ]
        result.winner = self.get_remap_obj("proposal", result.winner).pk
        strong_new_pairs = []
        for pair in result.strong_pairs:
            # [ [1,2], v]
            remapped = []
            for x in pair[0]:
                remapped.append(self.get_remap_obj("proposal", x).pk)
            strong_new_pairs.append([remapped, pair[1]])
        result.strong_pairs = strong_new_pairs
        if result.tied_winners:
            result.tied_winners = [
                self.get_remap_obj("proposal", x).pk for x in result.tied_winners
            ]

    def update_poll_results(self, deserialized: DeserializedObject):
        if not deserialized.object.result_data:
            return
        method_name = deserialized.object.method_name
        try:
            result = deserialized.object.result
        except Exception as exc:
            breakpoint()
            raise exc
        result.denied = [self.get_remap_obj("proposal", x).pk for x in result.denied]
        result.approved = [
            self.get_remap_obj("proposal", x).pk for x in result.approved
        ]
        if method_name == "combined_simple":
            result: CombinedSimplePollResult
            reformatted = {}
            for k, v in result.results.items():
                reformatted[self.get_remap_obj("proposal", k).pk] = v
            result.results = reformatted
        elif method_name == "majority":
            result: MajorityPollResult
            for prop_result in result.results:
                prop_result.proposal = self.get_remap_obj(
                    "proposal", prop_result.proposal
                ).pk
        elif method_name == "dutt":
            result: DuttResultSchema
            for prop_result in result.results:
                prop_result.proposal = self.get_remap_obj(
                    "proposal", prop_result.proposal
                ).pk
        elif method_name == "schulze":
            result: SchulzePollResult
            self.remap_schule_round(result)

        elif method_name == "repeated_schulze":
            result: RepeatedSchulzeResult
            result.candidates = [
                self.get_remap_obj("proposal", x).pk for x in result.candidates
            ]
            for res_round in result.rounds:
                self.remap_schule_round(res_round)
        elif method_name == "scottish_stv":
            result: STVResultSchema
            for stv_round in result.rounds:
                stv_round.selected = [
                    self.get_remap_obj("proposal", x).pk for x in stv_round.selected
                ]
                stv_round.vote_count = [
                    (self.get_remap_obj("proposal", k).pk, v)
                    for k, v in stv_round.vote_count
                ]
        else:
            breakpoint()
            raise ValueError(
                f"Need to handle remapping of results for method {method_name}"
            )
        # Just to make sure we don't use the wrong type!
        deserialized.object.result = result.dict()

    def update_special_fields(self, deserialized: DeserializedObject):
        field_names = [x.name for x in deserialized.object._meta.get_fields()]
        name = get_model_shortname(deserialized.object)
        importer = self.importers[name]
        pointer_val = None
        m2ms_handled = set()
        for model_name, attrs in importer.remap_relations.items():
            for relation_attr_name in attrs:
                if relation_attr_name in field_names:
                    # We need to handle m2m fields and simple FK relations
                    desc = deserialized.object._meta.get_field(relation_attr_name)
                    assert desc.is_relation
                    if desc.one_to_one or desc.many_to_one:
                        result = self.remap_fk_relation(
                            deserialized.object, relation_attr_name, model_name
                        )
                        if isinstance(result, int):
                            pointer_val = result
                    elif desc.one_to_many or desc.many_to_many:
                        if not desc.concrete:
                            f"Skipping model *{model_name}* non-concrete field {relation_attr_name}"
                            continue
                        assert relation_attr_name in deserialized.m2m_data
                        m2ms_handled.add(relation_attr_name)
                        # remapping m2m data
                        new_val = []
                        for pk in deserialized.m2m_data[relation_attr_name]:
                            remap_to = self.get_remap_obj(model_name, pk)
                            new_val.append(remap_to.pk)
                        deserialized.m2m_data[relation_attr_name] = new_val
        unhandled_m2m = {
            k for k, v in deserialized.m2m_data.items() if v
        } - m2ms_handled
        if unhandled_m2m:
            raise Exception(
                f"{deserialized.object} has undhandled m2ms: {unhandled_m2m}"
            )
        # Some models contain json fields. We'll load them in corresponding schema to check contents.
        # Note that PK isn't remapped yet!
        if name == "poll":
            for attr in ["settings", "result"]:
                self.verify_schema_attr(deserialized.object, attr)
        elif name == "vote":
            self.verify_schema_attr(deserialized.object, "vote")
        elif name == "speaker_system":
            self.verify_schema_attr(deserialized.object, "settings")

        # We need to force the pointer value for pk in case this model is a subclass of something
        if pointer_val:
            assert deserialized.object.pk == pointer_val
        else:
            # Set on save, any will do
            deserialized.object.pk = None
        if name == "poll":
            self.update_poll_results(deserialized)

    def verify_schema_attr(self, obj, attr):
        """
        Touch attributes that will validate stored json data.
        """
        try:
            getattr(obj, attr)
        except ValueError as exc:
            print(f"{obj} caused import error. Import PK: {obj.pk} - attr: {attr}")
            raise exc

    def save_obj(self, obj):
        saved = False
        if router.allow_migrate_model(self.using, obj.object.__class__):
            saved = True
            # FIXME: This is probably not needed, from the loaddata-script
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
