"""
Formularios del catálogo (categorías y productos) del frontend operativo.

Ninguno declara el campo `laundry`: el tenant lo asigna la vista desde la
sesión. El formulario solo recibe `laundry` para (a) acotar los <select> a
opciones del propio tenant y (b) validar unicidad de nombres POR lavandería
con un mensaje claro, en lugar de un error críptico de base de datos.
"""
from decimal import Decimal

from django import forms

from .models import Category, Product


class CategoryForm(forms.ModelForm):

    class Meta:
        model = Category
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'ej. Planchado, Tintorería, Edredones',
                'autofocus': True,
            }),
        }
        help_texts = {
            'name': 'Agrupa los servicios del menú; aparece como filtro en el catálogo y en el POS.',
        }

    def __init__(self, *args, laundry=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.laundry = laundry

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if name and self.laundry is not None:
            duplicated = (
                Category.objects.for_laundry(self.laundry)
                .filter(name__iexact=name)
                .exclude(pk=self.instance.pk)
                .exists()
            )
            if duplicated:
                raise forms.ValidationError(
                    'Ya existe una categoría con ese nombre en tu lavandería.'
                )
        return name


class ProductForm(forms.ModelForm):

    class Meta:
        model = Product
        fields = ['category', 'name', 'description', 'price']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'ej. Carga sencilla 8 kg', 'autofocus': True,
            }),
            'description': forms.Textarea(attrs={
                'rows': 3, 'placeholder': 'opcional · detalle visible en el catálogo',
            }),
            'price': forms.NumberInput(attrs={
                'step': '0.01', 'min': '0', 'inputmode': 'decimal',
                'placeholder': '0.00',
            }),
        }
        help_texts = {
            'price': 'Precio de catálogo en MXN. Las ventas pasadas conservan su precio congelado.',
        }

    def __init__(self, *args, laundry=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.laundry = laundry
        # El <select> de categoría SOLO ofrece las del propio tenant: una
        # categoría ajena "no es una opción válida" desde la raíz, así que ni
        # manipulando el POST se puede colgar un producto de otra lavandería.
        self.fields['category'].queryset = Category.objects.for_laundry(laundry)
        self.fields['category'].empty_label = 'Elige una categoría…'

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is not None and price < Decimal('0'):
            raise forms.ValidationError('El precio no puede ser negativo.')
        return price

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if name and self.laundry is not None:
            duplicated = (
                Product.objects.for_laundry(self.laundry)
                .filter(name__iexact=name)
                .exclude(pk=self.instance.pk)
                .exists()
            )
            if duplicated:
                raise forms.ValidationError(
                    'Ya existe un producto con ese nombre en tu lavandería.'
                )
        return name
