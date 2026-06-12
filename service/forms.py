"""
Formularios del punto de venta.

Reglas de oro:
  * Los <select> de cliente y producto se acotan al tenant ANTES de validar:
    un ID ajeno simplemente "no es una opción válida" (error de formulario,
    nunca una fuga).
  * El cajero solo captura producto y cantidad. Precio unitario, subtotal,
    total y folio son territorio exclusivo del backend.
"""
from decimal import Decimal

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from client.models import Client
from product.models import Product

from .models import Ticket, TicketDetail


class TicketForm(forms.ModelForm):
    """
    Cabecera de la venta: cliente (opcional), fecha estimada de entrega y
    anticipo. El cajero NUNCA captura saldo restante ni el estatus de pago:
    ambos los deriva el modelo (`_sync_payment_status`).
    """

    partial_payment = forms.DecimalField(
        required=False,
        min_value=Decimal('0'),
        max_digits=12,
        decimal_places=2,
        initial=0,
        label='Anticipo',
        widget=forms.NumberInput(attrs={
            'step': '0.01', 'min': '0', 'placeholder': '0.00', 'inputmode': 'decimal',
        }),
    )

    class Meta:
        model = Ticket
        fields = ['client', 'delivery_date_time', 'partial_payment']
        widgets = {
            # Input nativo de fecha/hora del navegador (formato ISO con 'T').
            'delivery_date_time': forms.DateTimeInput(
                attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M',
            ),
        }

    def __init__(self, *args, laundry=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.laundry = laundry
        client = self.fields['client']
        client.queryset = Client.objects.for_laundry(laundry).order_by('name')
        client.required = False
        client.empty_label = 'Público general (sin cliente)'

    def clean_partial_payment(self):
        # Campo opcional: vacío equivale a venta sin anticipo.
        return self.cleaned_data.get('partial_payment') or Decimal('0')


class TicketDetailForm(forms.ModelForm):
    """Línea de venta: producto del tenant + cantidad acotada.

    El tope de 9 999 piezas por línea no es capricho: evita que una cantidad
    absurda desborde los `max_digits` del subtotal y tire la petición con un
    error 500 de base de datos.
    """

    quantity = forms.IntegerField(min_value=1, max_value=9999, initial=1, label='Cantidad')

    class Meta:
        model = TicketDetail
        fields = ['product', 'quantity']

    def __init__(self, *args, laundry=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.for_laundry(laundry)


class BaseTicketDetailFormSet(BaseInlineFormSet):
    """Propaga el tenant a cada línea y exige al menos un producto."""

    def __init__(self, *args, laundry=None, **kwargs):
        self.laundry = laundry
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs['laundry'] = self.laundry
        return kwargs

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        lines = [
            form for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False)
        ]
        if not lines:
            raise forms.ValidationError('Agrega al menos un producto al ticket.')


TicketDetailFormSet = inlineformset_factory(
    Ticket,
    TicketDetail,
    form=TicketDetailForm,
    formset=BaseTicketDetailFormSet,
    fields=['product', 'quantity'],
    extra=0,
    can_delete=False,
    # Tope duro de líneas por ticket: corta de raíz un POST inflado a mano
    # (validate_max convierte el exceso en error de formulario, no en carga).
    max_num=200,
    validate_max=True,
)
