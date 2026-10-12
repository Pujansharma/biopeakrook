from django.db import migrations, models


class Migration(migrations.Migration):
    """Index for global reminder sweep: status + start_datetime window."""

    atomic = True

    dependencies = [
        (
            "appointments",
            "0024_associateavailabilityblock_uniq_active_google_block_per_event_and_more",
        ),
    ]

    operations = [
        migrations.AddIndex(
            model_name="appointment",
            index=models.Index(
                fields=["status", "start_datetime"],
                name="appointment_status_start_idx",
            ),
        ),
    ]
