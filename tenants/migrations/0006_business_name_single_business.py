"""
Paso previo a eliminar el modelo multi-tenant: el sistema pasa a gestionar un único negocio.

- Agrega BusinessProfile.name (antes vivía en Tenant.name) y lo copia.
- Aborta si hay más de un negocio cargado: al quitar tenant_id de todas las tablas
  sus datos se mezclarían. En ese caso hay que depurar la base antes de migrar.
"""
from django.db import migrations, models


def copy_business_name(apps, schema_editor):
    Tenant = apps.get_model('tenants', 'Tenant')
    BusinessProfile = apps.get_model('tenants', 'BusinessProfile')

    tenants = list(Tenant.objects.all())
    if len(tenants) > 1:
        slugs = ', '.join(t.slug for t in tenants)
        raise RuntimeError(
            f'Hay {len(tenants)} negocios cargados ({slugs}). El sistema pasa a ser de un solo '
            'negocio: eliminá los que sobran (y sus datos) antes de correr esta migración.'
        )
    if tenants:
        tenant = tenants[0]
        profile, _ = BusinessProfile.objects.get_or_create(tenant=tenant)
        profile.name = tenant.name
        profile.save(update_fields=['name'])


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0005_add_branding_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='businessprofile',
            name='name',
            field=models.CharField(default='', max_length=200),
        ),
        migrations.RunPython(copy_business_name, migrations.RunPython.noop),
    ]
