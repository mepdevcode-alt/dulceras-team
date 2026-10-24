"""
Roles sin referencia a multi-tenant: platform_owner -> superadmin, tenant_admin -> admin.
"""
from django.db import migrations, models

FORWARD = {'platform_owner': 'superadmin', 'tenant_admin': 'admin'}


def rename_roles(apps, schema_editor, mapping=FORWARD):
    User = apps.get_model('users', 'User')
    for old, new in mapping.items():
        User.objects.filter(role=old).update(role=new)


def restore_roles(apps, schema_editor):
    rename_roles(apps, schema_editor, {new: old for old, new in FORWARD.items()})


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_add_customer_role'),
    ]

    operations = [
        migrations.RunPython(rename_roles, restore_roles),
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('superadmin', 'Superadmin'),
                    ('admin', 'Administrador'),
                    ('staff_ventas', 'Staff Ventas'),
                    ('staff_produccion', 'Staff Producción'),
                    ('staff_caja', 'Staff Caja'),
                    ('customer', 'Cliente'),
                ],
                default='staff_ventas',
                max_length=30,
            ),
        ),
    ]
