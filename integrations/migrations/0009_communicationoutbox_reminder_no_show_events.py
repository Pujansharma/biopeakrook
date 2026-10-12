from django.db import migrations, models


class Migration(migrations.Migration):

    atomic = True

    dependencies = [
        ("integrations", "0008_communicationoutbox_uniq_comm_outbox_series_google_open_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="communicationoutbox",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("appointment_confirmed", "Appointment Confirmed"),
                    ("appointment_cancelled", "Appointment Cancelled"),
                    ("appointment_rescheduled", "Appointment Rescheduled"),
                    ("appointment_reminder", "Appointment Reminder"),
                    ("appointment_no_show", "Appointment No Show"),
                    ("associate_block_sync", "Associate Block Sync"),
                    ("associate_leave_sync", "Associate Leave Sync"),
                ],
                max_length=64,
            ),
        ),
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
                        ],
                    ),
                ),
                fields=("appointment", "channel", "event_type"),
                name="uniq_comm_outbox_appointment_channel_terminal_event",
            ),
        ),
    ]
