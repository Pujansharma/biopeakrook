from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0016_rename_customerprofile_is_onboarding_complete"),
    ]

    operations = [
        migrations.AddField(
            model_name="customerprofile",
            name="is_converted",
            field=models.BooleanField(
                default=True,
                help_text="False for shell profiles created at lead login; true after convert-client.",
            ),
        ),
    ]
