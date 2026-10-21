import uuid

from django.db import migrations, models


def populate_public_ids(apps, schema_editor):
    User = apps.get_model("users", "User")
    for user in User.objects.filter(public_id__isnull=True).iterator():
        user.public_id = uuid.uuid4()
        user.save(update_fields=["public_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0002_refreshtoken"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="public_id",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                null=True,
            ),
        ),
        migrations.RunPython(
            populate_public_ids,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="user",
            name="public_id",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
            ),
        ),
    ]
