"""
Grupos de permisos por defecto del POS.

El frontend muestra/oculta módulos con `{% if perms.app.codename %}` y las
vistas los exigen con `PermissionRequiredMixin`; esta migración garantiza que
existan dos roles listos para asignar desde el admin:

  * «Administradores de lavandería» — gestión completa de SU tenant
    (catálogo, clientes, inventario) + venta. Sin borrar tickets: las ventas
    son transacciones inmutables con folio consecutivo.
  * «Cajeros» — operación de mostrador: vender y dar de alta clientes;
    el catálogo y el inventario solo los consultan.

Las filas de Permission/ContentType se crean aquí mismo si aún no existen
(en una BD recién creada, post_migrate todavía no ha corrido cuando se
ejecuta esta migración); post_migrate las reutiliza después sin duplicar.
"""
from django.db import migrations

TENANT_ADMIN_GROUP = 'Administradores de lavandería'
CASHIER_GROUP = 'Cajeros'

# (app_label, modelo, acciones)
TENANT_ADMIN_PERMS = [
    ('client', 'client', ('view', 'add', 'change', 'delete')),
    ('product', 'category', ('view', 'add', 'change', 'delete')),
    ('product', 'product', ('view', 'add', 'change', 'delete')),
    ('inventory', 'inventory', ('view', 'add', 'change')),
    ('service', 'ticket', ('view', 'add')),
    ('service', 'ticketdetail', ('view', 'add')),
    ('laundries', 'laundrystaff', ('view',)),
]
CASHIER_PERMS = [
    ('client', 'client', ('view', 'add')),
    ('product', 'category', ('view',)),
    ('product', 'product', ('view',)),
    ('inventory', 'inventory', ('view',)),
    ('service', 'ticket', ('view', 'add')),
    ('service', 'ticketdetail', ('view', 'add')),
]


def _permission(apps, app_label, model, action):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    content_type, _ = ContentType.objects.get_or_create(app_label=app_label, model=model)
    permission, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename=f'{action}_{model}',
        defaults={'name': f'Can {action} {model}'},
    )
    return permission


def create_default_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for group_name, spec in (
        (TENANT_ADMIN_GROUP, TENANT_ADMIN_PERMS),
        (CASHIER_GROUP, CASHIER_PERMS),
    ):
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.add(*[
            _permission(apps, app_label, model, action)
            for app_label, model, actions in spec
            for action in actions
        ])


def noop(apps, schema_editor):
    # Al revertir no borramos los grupos: pueden tener usuarios asignados.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('laundries', '0002_laundrystaff'),
        ('client', '0002_remove_client_unique_client_email_per_laundry'),
        ('product', '0002_alter_product_options_and_more'),
        ('inventory', '0002_alter_inventory_options_inventory_laundry_and_more'),
        ('service', '0001_initial'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_default_groups, noop),
    ]
