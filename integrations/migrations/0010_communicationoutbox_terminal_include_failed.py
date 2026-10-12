from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Expand terminal unique to include FAILED so reminder sweep cannot insert a
    second row while the worker is still retrying a failed send.
    Atomic on PostgreSQL (single transaction).
    """

    atomic = True

    dependencies = [
        ("integrations", "0009_communicationoutbox_reminder_no_show_events"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="communicationoutbox",
            name="uniq_comm_outbox_appointment_channel_terminal_event",
        ),
        migrations.AddConstraint(
            model_name="communicationoutbox",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    (
                        "event_type__in",
                        [
                            "appointment_confirmed",
                            "appointment_cancelled",
                            "appointment_reminder",
                            "appointment_no_show",
                        ],
                    ),
                    (
                        "status__in",
                        [
                            "pending",
                            "sending",
                            "accepted",
                            "sent",
                            "delivered",
                            "read",
                            "failed",
                        ],
                    ),
                ),
                fields=("appointment", "channel", "event_type"),
                name="uniq_comm_outbox_appointment_channel_terminal_event",
            ),
        ),
    ]
