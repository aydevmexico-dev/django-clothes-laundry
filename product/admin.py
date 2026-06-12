from django.contrib import admin
from django.db.models import Count

from laundries.admin import TenantDataAdmin
from .models import Category, Product


@admin.register(Category)
class CategoryAdmin(TenantDataAdmin):
    list_display = ['name', 'laundry', 'product_count']
    list_filter = ['laundry']
    search_fields = ['name', 'laundry__name']  # requerido por el autocomplete de Producto
    list_select_related = ['laundry']
    autocomplete_fields = ['laundry']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_products=Count('products'))

    @admin.display(description='Productos', ordering='_products')
    def product_count(self, obj):
        return obj._products


@admin.register(Product)
class ProductAdmin(TenantDataAdmin):
    tenant_scoped_fks = ('category',)  # la categoría se limita al propio tenant

    list_display = ['name', 'category', 'price', 'laundry']
    list_editable = ['price']
    list_filter = ['laundry', 'category']
    search_fields = ['name', 'category__name']  # requerido por autocompletes (Ticket, Inventario)
    list_select_related = ['laundry', 'category']
    autocomplete_fields = ['laundry', 'category']
