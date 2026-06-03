from django.db import migrations, models


def state_to_enabled(apps, schema_editor):
    for model_name in ("MeetingComponent", "OrganisationComponent"):
        model = apps.get_model("components", model_name)
        model.objects.filter(state="on").update(enabled=True)


class Migration(migrations.Migration):

    dependencies = [
        ("components", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="meetingcomponent",
            name="enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="organisationcomponent",
            name="enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(state_to_enabled, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="meetingcomponent",
            name="state",
        ),
        migrations.RemoveField(
            model_name="organisationcomponent",
            name="state",
        ),
    ]
