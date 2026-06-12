"""
Módulo de ventas: punto de venta (POS), historial y recibo del ticket.

El precio unitario JAMÁS viaja en el formulario: lo congela el backend desde el
catálogo (`TicketDetail.save`). El frontend solo manda producto + cantidad, y
ambos se validan contra querysets acotados al tenant de la sesión.
"""
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DetailView, ListView

from laundries.mixins import TenantPermissionRequiredMixin, TenantQuerysetMixin
from product.models import Category, Product

from .forms import TicketDetailFormSet, TicketForm
from .models import Ticket


class TicketListView(TenantPermissionRequiredMixin, TenantQuerysetMixin, ListView):
    """Historial de ventas del tenant, con búsqueda por folio o cliente."""

    model = Ticket
    permission_required = 'service.view_ticket'
    template_name = 'service/ticket_list.html'
    context_object_name = 'tickets'
    paginate_by = settings.ITEMS_PER_PAGE

    def get_queryset(self):
        qs = super().get_queryset().select_related('client').order_by('-created_at')
        query = self.request.GET.get('q', '').strip()
        if query:
            qs = qs.filter(Q(folio__icontains=query) | Q(client__name__icontains=query))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '').strip()
        return context


class TicketDetailView(TenantPermissionRequiredMixin, TenantQuerysetMixin, DetailView):
    """
    Recibo de la venta. Como el queryset está acotado al tenant, pedir la PK de
    un ticket ajeno responde 404: para este usuario ese ticket no existe.
    """

    model = Ticket
    permission_required = 'service.view_ticket'
    template_name = 'service/ticket_detail.html'
    context_object_name = 'ticket'

    def get_queryset(self):
        return super().get_queryset().select_related('client').prefetch_related(
            'details__product'
        )


class TicketCreateView(TenantPermissionRequiredMixin, CreateView):
    """
    Punto de venta. Un ModelForm (cliente) + un inline formset (líneas).

    La interfaz visual (tarjetas de producto, ticket lateral) la monta app.js
    sobre el catálogo serializado con |json_script; el formulario y el formset
    de Django siguen siendo la única vía de entrada de datos, y el servidor
    es quien congela precios, calcula totales y asigna el folio.
    """

    model = Ticket
    form_class = TicketForm
    permission_required = ('service.add_ticket', 'service.add_ticketdetail')
    template_name = 'service/ticket_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['laundry'] = self.laundry
        return kwargs

    def get_detail_formset(self):
        kwargs = {'laundry': self.laundry}
        if self.request.method == 'POST':
            kwargs['data'] = self.request.POST
        return TicketDetailFormSet(**kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('detail_formset', self.get_detail_formset())

        # Catálogo del tenant para el tablero del POS (tarjetas + buscador).
        catalog = (
            Product.objects.for_laundry(self.laundry)
            .select_related('category')
            .order_by('category__name', 'name')
        )
        context['catalog'] = catalog
        context['categories'] = Category.objects.for_laundry(self.laundry)
        # Payload para app.js: precios como string para no perder centavos.
        context['catalog_payload'] = [
            {
                'id': product.pk,
                'name': product.name,
                'price': str(product.price),
                'category': product.category.name,
                'categoryId': product.category_id,
            }
            for product in catalog
        ]
        return context

    def form_valid(self, form):
        formset = self.get_detail_formset()
        if not formset.is_valid():
            return self.render_to_response(
                self.get_context_data(form=form, detail_formset=formset)
            )

        # El anticipo se valida contra el total PROSPECTIVO (precio de catálogo
        # × cantidad de cada línea) ANTES de crear nada: un anticipo mayor al
        # total se rechaza como error de formulario y NO consume folio (la
        # secuencia del tenant es monotónica y no debe gastarse en intentos).
        prospective_total = sum(
            (
                line.cleaned_data['product'].price * line.cleaned_data['quantity']
                for line in formset.forms
                if line.cleaned_data and not line.cleaned_data.get('DELETE', False)
            ),
            Decimal('0'),
        )
        partial = form.cleaned_data.get('partial_payment') or Decimal('0')
        if partial > prospective_total:
            form.add_error(
                'partial_payment',
                f'El anticipo (${partial}) no puede ser mayor que el total '
                f'de la venta (${prospective_total}).',
            )
            return self.render_to_response(
                self.get_context_data(form=form, detail_formset=formset)
            )

        # Ticket + líneas o nada: si algo falla no se consume folio ni queda
        # una venta a medias.
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.laundry = self.laundry      # tenant de la sesión, SIEMPRE
            self.object.save()                      # aquí se asigna el folio
            formset.instance = self.object
            formset.save()    # las señales recalculan total, saldo y estatus

        messages.success(self.request, f'Venta registrada con folio {self.object.folio}.')
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('service:ticket_detail', kwargs={'pk': self.object.pk})

    def form_invalid(self, form):
        formset = self.get_detail_formset()
        formset.is_valid()  # fuerza la validación para mostrar sus errores
        return self.render_to_response(
            self.get_context_data(form=form, detail_formset=formset)
        )


class TicketSettleView(TenantPermissionRequiredMixin, View):
    """
    Liquida el saldo restante de un ticket al entregar la ropa.

    Solo POST (acción que muta estado, con CSRF). El ticket se busca DENTRO
    del tenant de la sesión: liquidar la PK de otra lavandería es un 404.
    El monto no se captura: liquidar significa anticipo = total, y el modelo
    deriva saldo 0 y `paid=True` por sí mismo.
    """

    permission_required = 'service.change_ticket'
    http_method_names = ['post']

    def post(self, request, pk):
        ticket = get_object_or_404(
            Ticket.objects.for_laundry(self.laundry), pk=pk
        )
        if ticket.paid:
            messages.info(request, f'El ticket {ticket.folio} ya estaba liquidado.')
        else:
            ticket.partial_payment = ticket.total
            ticket.save()   # _sync_payment_status -> saldo 0, paid=True
            messages.success(
                request, f'Ticket {ticket.folio} liquidado por completo.'
            )
        return HttpResponseRedirect(
            reverse('service:ticket_detail', kwargs={'pk': ticket.pk})
        )
