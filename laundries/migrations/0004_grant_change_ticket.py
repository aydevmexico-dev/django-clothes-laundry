"""
Concede `service.change_ticket` a los dos roles del POS.

Con los nuevos campos financieros, liquidar el saldo al entregar la ropa es
una operación de mostrador: tanto cajeros como administradores de lavandería
necesitan poder ACTUALIZAR el ticket (la vista de liquidación lo exige).
El folio, el total y el detalle siguen siendo intocables: los protegen
`editable=False`, los `readonly_fields` del admin y la propia vista.
"""
from django.db import migrations

GROUPS = ('Administradores de lavandería', 'Cajeros')


def grant_change_ticket(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    Group = apps.get_model('auth', 'Group')

    content_type, _ = ContentType.objects.get_or_create(
        app_label='service', model='ticket'
    )
    permission, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename='change_ticket',
        defaults={'name': 'Can change ticket'},
    )
    for name in GROUPS:
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.add(permission)


def revoke_change_ticket(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    Group = apps.get_model('auth', 'Group')
    permission = Permission.objects.filter(
        codename='change_ticket', content_type__app_label='service'
    ).first()
    if permission is None:
        return
    for group in Group.objects.filter(name__in=GROUPS):
        group.permissions.remove(permission)


class Migration(migrations.Migration):

    dependencies = [
        ('laundries', '0003_default_groups'),
    ]

    operations = [
        migrations.RunPython(grant_change_ticket, revoke_change_ticket),
    ]
