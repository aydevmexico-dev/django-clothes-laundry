"""Directorio de clientes del tenant: consulta y alta desde mostrador."""
from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView

from laundries.mixins import TenantPermissionRequiredMixin, TenantQuerysetMixin

from .forms import ClientForm
from .models import Client


class ClientListView(TenantPermissionRequiredMixin, TenantQuerysetMixin, ListView):
    model = Client
    permission_required = 'client.view_client'
    template_name = 'client/client_list.html'
    context_object_name = 'clients'
    paginate_by = settings.ITEMS_PER_PAGE

    def get_queryset(self):
        qs = super().get_queryset()
        query = self.request.GET.get('q', '').strip()
        if query:
            # Mismo criterio que el admin: nombre y teléfono primero (familias
            # que comparten correo se distinguen por esos campos).
            qs = qs.filter(
                Q(name__icontains=query)
                | Q(phone_number__icontains=query)
                | Q(rfc__icontains=query)
                | Q(email__icontains=query)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '').strip()
        return context


class ClientCreateView(TenantPermissionRequiredMixin, CreateView):
    """
    Alta de cliente. El formulario NO incluye el campo lavandería: el tenant se
    asigna en el servidor desde la sesión, así que es imposible "sembrar" un
    cliente en otra lavandería manipulando el POST.
    """

    model = Client
    form_class = ClientForm
    permission_required = 'client.add_client'
    template_name = 'client/client_form.html'
    success_url = reverse_lazy('client:list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['laundry'] = self.laundry
        return kwargs

    def form_valid(self, form):
        form.instance.laundry = self.laundry
        response = super().form_valid(form)
        messages.success(self.request, f'Cliente «{self.object.name}» registrado.')
        return response
