from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0008_alter_product_callback_alter_provider_callback'),
        ('test_kit_inventory', '0003_testkitprovider_testkitproduct'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='TestKitProvider',
            new_name='Provider',
        ),
        migrations.RenameModel(
            old_name='TestKitProduct',
            new_name='Product',
        ),
        migrations.AlterModelTable(
            name='provider',
            table='test_kit_inventory_provider',
        ),
        migrations.AlterModelTable(
            name='product',
            table='test_kit_inventory_product',
        ),
        migrations.AlterField(
            model_name='provider',
            name='provider',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='test_kit_inventory_provider',
                to='products.provider',
            ),
        ),
        migrations.AlterField(
            model_name='product',
            name='provider',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='products',
                to='test_kit_inventory.provider',
            ),
        ),
    ]
