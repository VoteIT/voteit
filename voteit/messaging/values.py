"""Build wire payloads with ``.values()`` instead of a DRF serializer.

A collector that hands a serializer a queryset pays for a model instance and a
bound DRF field per row, for payloads that are almost always plain columns.
``.values()`` skips both -- measured between 2x and 6x faster, and 2-4x lighter,
across the collectors that use it. See ``voteit/messaging/CLAUDE.md``.

The catch is that a hand-written field list drifts away from the serializer the
moment someone adds a field, and nothing notices: the payload schemas are
permissive, so the key simply never appears on the wire. So the list is not
hand-written -- it is read off the serializer, and each app's collector tests
assert that both routes render byte-identical frames.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.serializers import BaseSerializer


@lru_cache(maxsize=None)
def wire_field_names(serializer_cls: type[BaseSerializer]) -> tuple[str, ...]:
    """The keys ``serializer_cls`` puts on the wire, in declaration order.

    Reads the instantiated serializer rather than ``Meta.fields``, so it also
    covers the serializers that declare ``Meta.exclude`` and the ones that
    override a model field with a declared one. Write-only fields never reach a
    payload, so they are left out.

    >>> from voteit.notes.rest_api.serializers import NoteSerializer
    >>> wire_field_names(NoteSerializer)
    ('pk', 'agenda_item', 'meeting', 'created', 'proposal', 'user', 'body', 'intent')
    """
    return tuple(
        name for name, field in serializer_cls().fields.items() if not field.write_only
    )


def wire_values(
    serializer_cls: type[BaseSerializer], qs: QuerySet, **aliases
) -> QuerySet:
    """``qs.values()`` yielding exactly the keys ``serializer_cls`` would.

    ``aliases`` are for the fields that are not columns on the model -- pass a
    query expression per field, e.g. ``room=F("speaker_list__room_id")`` where
    the serializer declares ``source="speaker_list.room"``. They are the one
    thing written by hand, so they are checked against the serializer here
    rather than silently adding a key the REST representation does not have.

    Everything else has to be a plain column. ``.values()`` raises FieldError
    otherwise, which is the point: a ``SerializerMethodField`` added to the
    serializer fails loudly here instead of quietly going missing from the
    payload.

    >>> from django.db.models import F
    >>> from voteit.speaker.models import Speaker
    >>> from voteit.speaker.rest_api.serializers import SpeakerSerializer
    >>> qs = wire_values(
    ...     SpeakerSerializer, Speaker.objects.all(), room=F("speaker_list__room_id")
    ... )
    >>> sorted(qs.query.values_select + tuple(qs.query.annotations))
    ['pk', 'room', 'seconds', 'speaker_list', 'started', 'user']

    An alias the serializer does not produce is a mistake, not a free extra:

    >>> wire_values(SpeakerSerializer, Speaker.objects.all(), nope=F("pk"))
    Traceback (most recent call last):
    ...
    ValueError: SpeakerSerializer does not produce ['nope']
    """
    names = wire_field_names(serializer_cls)
    unknown = sorted(set(aliases) - set(names))
    if unknown:
        raise ValueError(f"{serializer_cls.__name__} does not produce {unknown}")
    return qs.values(*(n for n in names if n not in aliases), **aliases)
