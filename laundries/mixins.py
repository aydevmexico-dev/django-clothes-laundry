"""
Mixins de aislamiento multi-tenant para las vistas del frontend (no-admin).

Filosofía (la misma que `laundries.admin`): el tenant NUNCA viaja en la URL ni
en el formulario; se resuelve SIEMPRE desde la sesión autenticada vía
`LaundryStaff`. Así es imposible "adivinar" la lavandería de otro cambiando un
ID en la barra de direcciones: no existe tal ID que cambiar.
"""
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .models import LaundryStaff


def get_membership(request):
    """
    Devuelve el `LaundryStaff` del usuario logueado (o None), cacheado en el
    request para que vista + context processor compartan UNA sola consulta.
    """
    if not hasattr(request, '_tenant_membership'):
        membership = None
        if request.user.is_authenticated:
            membership = (
                LaundryStaff.objects
                .filter(user=request.user)
                .select_related('laundry')
                .first()
            )
        request._tenant_membership = membership
    return request._tenant_membership


class TenantRequiredMixin(LoginRequiredMixin):
    """
    Exige sesión activa Y pertenencia a una lavandería activa.

    Resuelve y expone `self.laundry` / `self.membership` antes de que corra la
    vista, de modo que `get_queryset()` y `get_context_data()` siempre tengan
    el tenant a mano. Casos límite:

      * Anónimo               -> redirige al login conservando ?next=.
      * Superusuario sin
        membresía             -> es staff global: se le manda al /admin/.
      * Usuario sin membresía -> 403 (fail-safe: jamás "ve" datos de nadie).
      * Lavandería inactiva   -> 403 (el tenant fue suspendido).
    """

    permission_denied_message = 'Tu usuario no tiene una lavandería asignada o está inactiva.'

    def handle_no_permission(self):
        # Sin sesión SIEMPRE se redirige al login; con sesión pero sin permiso
        # respondemos 403 explícito (nunca un redirect-loop hacia el login).
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        raise PermissionDenied(self.get_permission_denied_message())

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        membership = get_membership(request)
        if membership is None:
            if request.user.is_superuser:
                # El staff global no opera cajas: su panel es el admin.
                return redirect('admin:index')
            return self.handle_no_permission()
        if not membership.laundry.is_active:
            return self.handle_no_permission()

        self.membership = membership
        self.laundry = membership.laundry

        if not self.check_tenant_access():
            return self.handle_no_permission()

        return super().dispatch(request, *args, **kwargs)

    def check_tenant_access(self):
        """Hook para reglas extra de acceso (ya con `self.membership` resuelto)."""
        return True


class TenantPermissionRequiredMixin(TenantRequiredMixin, PermissionRequiredMixin):
    """
    Membresía de tenant + permisos nativos de Django (`permission_required`).

    El orden del MRO importa: primero se resuelve el tenant (TenantRequired) y
    después se valida el permiso de modelo (PermissionRequired). El 403 de
    permisos reutiliza nuestro `handle_no_permission`.
    """

    permission_denied_message = 'No tienes permiso para usar este módulo.'


class TenantQuerysetMixin:
    """
    Acota el queryset de ListView/DetailView a la lavandería del usuario.

    Al filtrar DENTRO de `get_queryset()`, un DetailView con la PK de otro
    tenant responde 404: para el usuario, los datos ajenos NO existen.
    """

    tenant_lookup = 'laundry'

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(**{self.tenant_lookup: self.laundry})


class TenantAdminRequiredMixin(TenantRequiredMixin):
    """Solo para administradores del tenant (`LaundryStaff.is_tenant_admin`)."""

    permission_denied_message = 'Esta sección es exclusiva del administrador de la lavandería.'

    def check_tenant_access(self):
        return super().check_tenant_access() and self.membership.is_tenant_admin
