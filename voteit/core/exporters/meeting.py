from typing import Optional
from typing import Union

from django.db.models import Model
from django.db.models import QuerySet
from typing import List

from typing import Set

from typing import Generator

from django.utils.functional import cached_property
from typing import Iterator
from voteit.core.utils import get_content_registry
from voteit.core.utils import get_model_by_shortname
from voteit.core.utils import get_model_shortname


class MeetingExport:
    def __init__(
        self,
        model,
        meeting_kw="meeting",
        global_ignore_fields=None,
        ignore_fields: set = (),
        meeting: int = None,
    ):
        self.model = model
        self.meeting = meeting
        self.meeting_kw = meeting_kw
        self.ignore_fields = set(ignore_fields)
        if global_ignore_fields:
            self.ignore_fields.update(global_ignore_fields)

    @cached_property
    def qs(self):
        return self.model.objects.filter(**{self.meeting_kw: self.meeting})

    def __call__(self) -> QuerySet:
        return self.qs

    def __bool__(self):
        return self.qs.exists()

    def __len__(self):
        return self.qs.count()

    @property
    def select_fields(self) -> Optional[Set[str]]:
        if self.ignore_fields:
            concrete_model = self.model._meta.concrete_model
            return set(
                [
                    x.name
                    for x in concrete_model._meta.fields
                    if x.name not in self.ignore_fields
                ]
            )


DEFAULT_IGNORE_FIELDS = (
    "created",
    "last_modified_by",
    "modified",
    "related_modified",
    "start_time",
    "end_time",
)


class MeetingExporters:
    """
    Export a meeting and all related objects. The purpose of using this instead of just dump is to select
    meeting related things only, so we're able to duplicate a meeting.
    """

    def __init__(self, meeting: int, ignore_fields=DEFAULT_IGNORE_FIELDS):
        assert isinstance(meeting, int)
        self.meeting = meeting
        self.ignore_fields = ignore_fields
        self._data = None

    @staticmethod
    def get_exportable_models():
        reg = get_content_registry()
        for v in reg.values():
            if exporters := getattr(v, "exporters", None):
                if "meeting" in exporters:
                    yield v

    def get_object_count(self) -> int:
        return sum([len(x) for x in self])

    @property
    def data(self) -> dict:
        if self._data is None:
            self._data = {}
            for model in self.get_exportable_models():
                self._data[get_model_shortname(model)] = MeetingExport(
                    model,
                    meeting=self.meeting,
                    global_ignore_fields=self.ignore_fields,
                    **model.exporters["meeting"],
                )
        return self._data

    def __iter__(self) -> Iterator[MeetingExport]:
        return iter(self.data.values())

    def __getitem__(self, item: Union[str, Model]) -> MeetingExport:
        if isinstance(item, Model):
            item = get_model_shortname(item)
        return self.data[item]
