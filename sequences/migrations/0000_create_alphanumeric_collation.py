# DO NOT SQUASH OR DELETE THIS MIGRATION
# This migration creates the alphanumeric collation required for proper sorting
# throughout the sequences application. It must remain as a separate migration.

from django.contrib.postgres.operations import CreateCollation
from django.db import migrations


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0001_initial'),
    ]

    operations = [
        CreateCollation(
            provider='icu',
            name='alphanumeric',
            locale='en-u-kn',
            deterministic=True,
        ),
    ]
