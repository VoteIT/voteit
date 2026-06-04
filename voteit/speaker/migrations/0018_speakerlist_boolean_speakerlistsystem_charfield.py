from django.db import migrations
from django.db import models


def convert_state_to_boolean(apps, schema_editor):
    SpeakerList = apps.get_model("speaker", "SpeakerList")
    SpeakerList.objects.filter(state="closed").update(is_open=False)


class Migration(migrations.Migration):

    dependencies = [
        ("speaker", "0017_speakerlist_meeting_speakerlist_room"),
    ]

    operations = [
        # SpeakerList: add is_open BooleanField (default True), data-migrate, remove state
        migrations.AddField(
            model_name="speakerlist",
            name="is_open",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(
            convert_state_to_boolean,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="speakerlist",
            name="state",
        ),
        # SpeakerListSystem: FSMField → CharField
        migrations.AlterField(
            model_name="speakerlistsystem",
            name="state",
            field=models.CharField(
                choices=[
                    ("inactive", "Inactive"),
                    ("active", "Active"),
                    ("archived", "Archived"),
                ],
                default="active",
                max_length=20,
            ),
        ),
    ]
