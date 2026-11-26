from collections import defaultdict
from random import sample
from string import ascii_lowercase

import django.db.models.functions.text
from django.db import migrations, models
from django.utils.text import slugify

MAX_LENGTH = 100


def _fit(base: str, suffix: str) -> str:
    return base[: MAX_LENGTH - len(suffix)] + suffix


def fill_blanks(apps, schema_editor):
    MeetingGroup = apps.get_model("meeting", "MeetingGroup")
    for group in MeetingGroup.objects.filter(
        models.Q(groupid__isnull=True) | models.Q(groupid="")
    ):
        taken = set(
            MeetingGroup.objects.filter(meeting_id=group.meeting_id).values_list(
                "groupid", flat=True
            )
        )
        base = (slugify(group.title) or "".join(sample(ascii_lowercase, 8)))[
            :MAX_LENGTH
        ]
        groupid, i = base, 0
        while groupid in taken:
            i += 1
            groupid = _fit(base, f"-{i}")
        group.groupid = groupid
        group.save(update_fields=["groupid"])
    for group in MeetingGroup.objects.filter(title=""):
        group.title = group.groupid
        group.save(update_fields=["title"])


def rename_duplicate_titles(apps, schema_editor):
    """Keep the oldest title in each case-insensitive cluster, suffix the rest with groupid."""
    MeetingGroup = apps.get_model("meeting", "MeetingGroup")
    dupes = (
        MeetingGroup.objects.annotate(lt=django.db.models.functions.text.Lower("title"))
        .values("meeting_id", "lt")
        .annotate(n=models.Count("id"))
        .filter(n__gt=1)
    )
    meeting_ids = {row["meeting_id"] for row in dupes}
    for meeting_id in meeting_ids:
        groups = list(
            MeetingGroup.objects.filter(meeting_id=meeting_id).order_by("created", "pk")
        )
        used = set()
        clusters = defaultdict(list)
        for group in groups:
            clusters[group.title.lower()].append(group)
        for cluster in clusters.values():
            used.add(cluster[0].title.lower())
        for cluster in clusters.values():
            for group in cluster[1:]:
                title = _fit(group.title, f" ({group.groupid})")
                if title.lower() in used:
                    title = _fit(group.title, f" ({group.groupid}-{group.pk})")
                used.add(title.lower())
                group.title = title
                group.save(update_fields=["title"])


class Migration(migrations.Migration):
    dependencies = [
        ("meeting", "0031_alter_groupmembership_user"),
    ]

    operations = [
        migrations.RunPython(fill_blanks, migrations.RunPython.noop),
        migrations.RunPython(rename_duplicate_titles, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="meetinggroup",
            name="groupid",
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name="meetinggroup",
            name="title",
            field=models.CharField(max_length=100),
        ),
        migrations.AddConstraint(
            model_name="meetinggroup",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("title"),
                models.F("meeting"),
                name="unique_meeting_group_title_ci",
                violation_error_message="A group with that title already exists.",
            ),
        ),
    ]
