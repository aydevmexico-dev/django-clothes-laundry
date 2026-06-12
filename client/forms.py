"""Formularios de clientes del frontend operativo."""
import re

from django import forms
from django.core.validators import RegexValidator

from .models import Client

# RFC del SAT: 3-4 letras (incluye Ñ y &), fecha AAMMDD y homoclave de 3.
RFC_PATTERN = re.compile(r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$')


class ClientForm(forms.ModelForm):
    """
    Alta/edición de cliente SIN campo de lavandería: el tenant lo pone la vista
    desde la sesión. El formulario recibe `laundry` solo para validar unicidad
    del RFC dentro del propio tenant con un mensaje claro.
    """

    class Meta:
        model = Client
        fields = ['name', 'phone_number', 'email', 'rfc', 'address']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'ej. María González', 'autofocus': True,
            }),
            'phone_number': forms.TextInput(attrs={
                'placeholder': '10 dígitos', 'inputmode': 'numeric',
            }),
            'email': forms.EmailInput(attrs={'placeholder': 'opcional'}),
            'rfc': forms.TextInput(attrs={
                'placeholder': 'opcional · 12-13 caracteres',
                'class': 'input--uppercase',
            }),
            'address': forms.Textarea(attrs={'rows': 3, 'placeholder': 'opcional'}),
        }

    def __init__(self, *args, laundry=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.laundry = laundry
        # Teléfono mexicano de mostrador: exactamente 10 dígitos (si se captura).
        self.fields['phone_number'].validators.append(
            RegexValidator(r'^\d{10}$', 'El teléfono debe tener exactamente 10 dígitos.')
        )

    def clean_rfc(self):
        rfc = (self.cleaned_data.get('rfc') or '').strip().upper() or None
        if rfc and not RFC_PATTERN.match(rfc):
            raise forms.ValidationError(
                'El RFC no tiene un formato válido (ej. GOMA820301AB1 o XAXX010101000).'
            )
        if rfc and self.laundry is not None:
            duplicated = (
                Client.objects.for_laundry(self.laundry)
                .filter(rfc=rfc)
                .exclude(pk=self.instance.pk)
                .exists()
            )
            if duplicated:
                raise forms.ValidationError('Ya existe un cliente con ese RFC en tu lavandería.')
        return rfc
