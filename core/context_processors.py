"""Context processors a nivel de proyecto."""
from django.apps import apps

# Apps de Django que nunca aparecen en la barra lateral de negocio.
_HIDDEN_APP_PREFIXES = ('django.',)
_HIDDEN_APP_NAMES = {'core'}


def sidebar_apps(request):
    """
    Expone las apps de negocio del POS para construir una barra lateral de
    navegación en las plantillas (variable de contexto `sidebar_apps`).

    Recorre el registro de apps de Django, descarta las de framework y deja las
    propias (lavanderías, clientes, productos, inventario…) junto con los
    modelos que registran, para enlazarlos desde el menú.
    """
    items = []
    for config in apps.get_app_configs():
        if config.name in _HIDDEN_APP_NAMES:
            continue
        if config.name.startswith(_HIDDEN_APP_PREFIXES):
            continue
        models = list(config.get_models())
        if not models:
            continue
        items.append({
            'label': config.label,
            'name': config.verbose_name,
            'models': [model._meta.verbose_name_plural for model in models],
        })
    return {'sidebar_apps': items}


def tenant(request):
    """
    Expone en TODAS las plantillas la lavandería del usuario logueado:

      * `tenant`            -> la Laundry de la sesión (o None)
      * `tenant_membership` -> el registro LaundryStaff completo
      * `is_tenant_admin`   -> bool, para la navegación condicional del sidebar

    Comparte caché por-request con los mixins (`get_membership`), así que
    plantilla + vista cuestan UNA sola consulta por petición.
    """
    # Import local: este módulo lo carga el motor de plantillas y no debe
    # importar modelos durante el arranque de la configuración.
    from laundries.mixins import get_membership

    membership = get_membership(request) if hasattr(request, 'user') else None
    return {
        'tenant': membership.laundry if membership else None,
        'tenant_membership': membership,
        'is_tenant_admin': bool(membership and membership.is_tenant_admin),
    }
