from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("agenda", "0008_alter_agendaitem_state"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="agendaitem",
            name="related_modified",
        ),
    ]
