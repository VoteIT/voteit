from django.db import migrations


def backfill_voter_data(apps, schema_editor):
    ElectoralRegister = apps.get_model("poll", "ElectoralRegister")
    VoterWeight = apps.get_model("poll", "VoterWeight")
    to_update = []
    for er in ElectoralRegister.objects.all().iterator(chunk_size=500):
        er.voter_data = {
            str(vw["user_id"]): vw["weight"]
            for vw in VoterWeight.objects.filter(register=er).values("user_id", "weight")
        }
        to_update.append(er)
        if len(to_update) >= 500:
            ElectoralRegister.objects.bulk_update(to_update, ["voter_data"])
            to_update.clear()
    if to_update:
        ElectoralRegister.objects.bulk_update(to_update, ["voter_data"])


class Migration(migrations.Migration):

    dependencies = [
        ("poll", "0013_add_voter_data"),
    ]

    operations = [
        migrations.RunPython(backfill_voter_data, migrations.RunPython.noop),
    ]
