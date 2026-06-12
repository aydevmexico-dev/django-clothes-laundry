from django.contrib import admin

from laundries.admin import TenantDataAdmin
from .models import Client


@admin.register(Client)
class ClientAdmin(TenantDataAdmin):
    list_display = ['name', 'phone_number', 'email', 'rfc', 'laundry']
    list_filter = ['laundry']
    # Como el email ya no es único, el cajero distingue a los familiares que lo
    # comparten por NOMBRE y TELÉFONO (van primero); rfc/email quedan como apoyo.
    search_fields = ['name', 'phone_number', 'rfc', 'email']
    list_select_related = ['laundry']
    autocomplete_fields = ['laundry']
