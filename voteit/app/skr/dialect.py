from __future__ import annotations
import os.path

from django.conf import settings
from pydantic import field_validator, Field, StringConstraints, BaseModel

from voteit.app.skr import FILE_KOMMUNER
from voteit.app.skr import FILE_REGIONER
from voteit.app.skr import KOMMUN_TAG
from voteit.app.skr import REGION_TAG
from voteit.meeting.dialects import DialectScript
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from typing import List
from typing_extensions import Annotated


class CSVRows(BaseModel):
    rows: Annotated[
        List[
            Annotated[
                List[Annotated[str, StringConstraints(strip_whitespace=True)]],
                Field(
                    min_length=2,
                    max_length=2,
                ),
            ]
        ],
        Field(
            min_length=1,
            max_length=500,
        ),
    ]

    @field_validator("rows", mode="before")
    @classmethod
    def transform_rows(cls, v):
        if isinstance(v, (list, tuple)):
            return [item.split("\t") if isinstance(item, str) else item for item in v]
        return v


class CreateSKRGroups(DialectScript):
    def install(self, meeting: Meeting):
        regioner_file = os.path.join(
            settings.MEETING_DIALECTS_DIR, "data", FILE_REGIONER
        )
        kommuner_file = os.path.join(
            settings.MEETING_DIALECTS_DIR, "data", FILE_KOMMUNER
        )
        objs = [MeetingGroup(groupid="skr", meeting=meeting, title="SKR")]
        objs.extend(self.mk_bulk_objs(regioner_file, REGION_TAG, meeting))
        objs.extend(self.mk_bulk_objs(kommuner_file, KOMMUN_TAG, meeting))
        MeetingGroup.objects.bulk_create(objs)

    def mk_bulk_objs(self, fn, tag, meeting):
        with open(fn, "r") as f:
            data = CSVRows(rows=f.readlines())
            for row in data.rows:
                yield MeetingGroup(
                    meeting=meeting, groupid=row[0].lower(), title=row[1], tags=[tag]
                )
            # In case this dialect is ever installable for an existing meeting, we may need to change this
            # for row in data.rows:
            #     meeting.groups.update_or_create(
            #         groupid=row[0], defaults={"title": row[1], "tags": [tag]}
            #     )
