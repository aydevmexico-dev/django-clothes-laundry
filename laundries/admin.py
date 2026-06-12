from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Count

from .models import Laundry, LaundryStaff


def get_user_laundry(request):
    """
    Devuelve la lavandería del staff logueado, o None si es superusuario/global.

    El resultado se cachea en el request para no repetir la consulta en cada
    método del ModelAdmin (get_queryset, formfield_for_foreignkey, save_model…).
    """
    if not hasattr(request, '_tenant_laundry'):
        membership = (
            LaundryStaff.objects
            .filter(user=request.user)
            .select_related('laundry')
            .first()
        )
        request._tenant_laundry = membership.laundry if membership else None
    return request._tenant_laundry


# ---------------------------------------------------------------------------
# Mixins reutilizables de aislamiento multi-tenant
# ---------------------------------------------------------------------------
class TenantQuerysetMixin:
    """Acota el queryset del admin a la lavandería del usuario (salvo superusuario)."""

    tenant_lookup = 'laundry'  # lookup ORM desde este modelo hasta la Laundry

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        laundry = get_user_laundry(request)
        if laundry is None:
            # Staff sin lavandería asignada: no ve nada (fail-safe).
            return qs.none()
        return qs.filter(**{self.tenant_lookup: laundry})


class TenantDataAdmin(TenantQuerysetMixin, admin.ModelAdmin):
    """
    Base para los modelos de datos del tenant (Categoría, Cliente, Producto).

    Además de filtrar el listado:
      * oculta el selector de lavandería al admin local y se la asigna sola;
      * restringe los choices de FKs internos (p. ej. la categoría de un producto)
        a los del propio tenant;
      * elimina el filtro «por lavandería» cuando es redundante.
    """

    tenant_lookup = 'laundry'
    tenant_scoped_fks = ()  # otros FKs a filtrar por tenant, p. ej. ('category',)

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if not request.user.is_superuser:
            # Para el admin local el filtro por lavandería no aporta nada.
            list_filter = [f for f in list_filter if f != 'laundry']
        return list_filter

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or [])
        if not request.user.is_superuser and 'laundry' not in exclude:
            exclude.append('laundry')
        return exclude

    def save_model(self, request, obj, form, change):
        # El admin local nunca elige tenant: se le asigna el suyo automáticamente.
        if not request.user.is_superuser and not obj.laundry_id:
            obj.laundry = get_user_laundry(request)
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            laundry = get_user_laundry(request)
            if laundry is not None:
                if db_field.name == 'laundry':
                    kwargs['queryset'] = Laundry.objects.filter(pk=laundry.pk)
                elif db_field.name in self.tenant_scoped_fks:
                    kwargs['queryset'] = db_field.related_model.objects.filter(
                        laundry=laundry
                    )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ---------------------------------------------------------------------------
# Alta de lavandería + su administrador en una sola pantalla
# ---------------------------------------------------------------------------
class LaundryStaffInline(admin.TabularInline):
    """Permite ver/asignar usuarios existentes desde el detalle de la lavandería."""

    model = LaundryStaff
    extra = 0
    autocomplete_fields = ['user']
    verbose_name = 'Usuario asignado'
    verbose_name_plural = 'Usuarios asignados'


class LaundryAdminForm(forms.ModelForm):
    """Añade campos opcionales para crear el Tenant Admin en el mismo formulario."""

    admin_username = forms.CharField(
        required=False,
        label='Usuario administrador',
        help_text='Opcional: crea aquí mismo al responsable de la lavandería.',
    )
    admin_email = forms.EmailField(required=False, label='Correo del administrador')
    admin_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput,
        label='Contraseña temporal',
    )

    class Meta:
        model = Laundry
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        username = (cleaned.get('admin_username') or '').strip()
        if username:
            User = get_user_model()
            if User.objects.filter(username=username).exists():
                self.add_error('admin_username', 'Ya existe un usuario con ese nombre.')
            if not cleaned.get('admin_password'):
                self.add_error('admin_password', 'Define una contraseña temporal.')
        return cleaned


@admin.register(Laundry)
class LaundryAdmin(TenantQuerysetMixin, admin.ModelAdmin):
    tenant_lookup = 'pk'  # la Laundry ES el tenant: se filtra por su propia PK
    form = LaundryAdminForm
    inlines = [LaundryStaffInline]

    list_display = ['name', 'prefix', 'is_active', 'staff_count', 'product_count', 'created_at']
    list_editable = ['is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'prefix']  # requerido por los autocomplete que apuntan aquí

    def get_readonly_fields(self, request, obj=None):
        ro = ['folio_counter', 'created_at']
        if obj is not None:
            ro.append('prefix')  # tras el alta el prefijo queda congelado
        return ro

    def get_fieldsets(self, request, obj=None):
        main = (None, {'fields': ['name', 'prefix', 'is_active']})
        if obj is None and request.user.is_superuser:
            return [
                main,
                ('Alta rápida del administrador (opcional)', {
                    'fields': ['admin_username', 'admin_email', 'admin_password'],
                    'description': 'Crea en un solo paso el usuario responsable de esta lavandería.',
                }),
            ]
        return [main, ('Control interno', {'fields': ['folio_counter', 'created_at']})]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _staff=Count('staff', distinct=True),
            _products=Count('products', distinct=True),
        )

    @admin.display(description='Usuarios', ordering='_staff')
    def staff_count(self, obj):
        return obj._staff

    @admin.display(description='Productos', ordering='_products')
    def product_count(self, obj):
        return obj._products

    def has_add_permission(self, request):
        # Solo el staff global da de alta nuevas lavanderías.
        return request.user.is_superuser

    # -- Desmontaje del tenant -------------------------------------------
    # Product.category usa PROTECT, así que la cascada normal de la lavandería
    # falla con ProtectedError. Eliminamos primero los productos (única relación
    # protegida) y dejamos que la cascada se encargue del resto, de forma atómica.
    @staticmethod
    def _teardown(laundries):
        from product.models import Product

        ids = [obj.pk for obj in laundries]
        with transaction.atomic():
            Product.objects.filter(laundry_id__in=ids).delete()
            Laundry.objects.filter(pk__in=ids).delete()

    def delete_model(self, request, obj):
        self._teardown([obj])

    def delete_queryset(self, request, queryset):
        self._teardown(queryset)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            return
        username = (form.cleaned_data.get('admin_username') or '').strip()
        if not username:
            return
        User = get_user_model()
        user = User.objects.create_user(
            username=username,
            email=form.cleaned_data.get('admin_email') or '',
            password=form.cleaned_data['admin_password'],
            is_staff=True,
        )
        group, _ = Group.objects.get_or_create(name='Administradores de lavandería')
        user.groups.add(group)
        LaundryStaff.objects.create(user=user, laundry=obj, is_tenant_admin=True)
        self.message_user(
            request,
            f'Usuario administrador «{username}» creado y asignado a {obj.name}.',
        )


@admin.register(LaundryStaff)
class LaundryStaffAdmin(TenantQuerysetMixin, admin.ModelAdmin):
    list_display = ['user', 'laundry', 'is_tenant_admin']
    list_filter = ['is_tenant_admin', 'laundry']
    search_fields = ['user__username', 'user__email', 'laundry__name']
    list_select_related = ['user', 'laundry']
    autocomplete_fields = ['user', 'laundry']
