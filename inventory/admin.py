from django.contrib import admin

from laundries.admin import TenantDataAdmin
from .models import Inventory


@admin.register(Inventory)
class InventoryAdmin(TenantDataAdmin):
    tenant_scoped_fks = ('product',)  # solo productos del propio tenant

    list_display = ['product', 'laundry', 'quantity', 'last_updated']
    list_editable = ['quantity']
    list_filter = ['laundry']
    search_fields = ['product__name']
    list_select_related = ['product', 'laundry']
    autocomplete_fields = ['product']
    readonly_fields = ['last_updated']
