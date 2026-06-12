from django.contrib import admin

from laundries.admin import TenantDataAdmin, get_user_laundry
from product.models import Product
from .models import Ticket, TicketDetail


class TicketDetailInline(admin.TabularInline):
    model = TicketDetail
    extra = 1
    autocomplete_fields = ['product']
    # El cajero SOLO captura Producto y Cantidad. El precio unitario (heredado del
    # catálogo y congelado) y el subtotal los calcula el backend: aquí son de solo
    # lectura, así que ni se pueden teclear ni se validan como requeridos en el form.
    fields = ['product', 'quantity', 'unit_price', 'subtotal']
    readonly_fields = ['unit_price', 'subtotal']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # El admin local solo puede vender productos de su propia lavandería.
        if db_field.name == 'product' and not request.user.is_superuser:
            laundry = get_user_laundry(request)
            if laundry is not None:
                kwargs['queryset'] = Product.objects.filter(laundry=laundry)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Ticket)
class TicketAdmin(TenantDataAdmin):
    inlines = [TicketDetailInline]
    list_display = [
        'folio', 'laundry', 'client', 'total',
        'remaining_balance', 'paid', 'delivery_date_time', 'created_at',
    ]
    list_filter = ['laundry', 'paid', 'created_at']
    search_fields = ['folio', 'client__name']
    date_hierarchy = 'created_at'
    autocomplete_fields = ['laundry', 'client']
    list_select_related = ['laundry', 'client']
    # Folio y total se calculan solos; nunca se editan a mano. Saldo restante
    # y ¿Pagado? son derivados (editable=False en el modelo): aquí solo se
    # MUESTRAN; el único campo financiero capturable es el anticipo.
    readonly_fields = [
        'folio', 'folio_number', 'total',
        'remaining_balance', 'paid', 'created_at',
    ]
