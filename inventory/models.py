from django.core.exceptions import ValidationError
from django.db import models

from laundries.models import Laundry, TenantManager
from product.models import Product


class Inventory(models.Model):
    """
    Existencias de un producto. La relación con el producto es OneToOne, así que
    hay como máximo UN registro de stock por producto; y como cada producto
    pertenece a una sola lavandería, el stock queda unívoco por (producto, tenant).
    """

    laundry = models.ForeignKey(
        Laundry,
        on_delete=models.CASCADE,
        related_name='inventory_items',
        editable=False,  # se deriva del producto; no se elige a mano
        verbose_name='Lavandería',
    )
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='inventory',
        verbose_name='Producto',
    )
    quantity = models.PositiveIntegerField(default=0, verbose_name='Cantidad')
    last_updated = models.DateTimeField(auto_now=True, verbose_name='Última actualización')

    objects = TenantManager()

    class Meta:
        verbose_name = 'Inventario'
        verbose_name_plural = 'Inventarios'
        ordering = ['product__name']

    def __str__(self):
        return f'{self.product.name} — {self.quantity}'

    def clean(self):
        if self.product_id and self.laundry_id and self.product.laundry_id != self.laundry_id:
            raise ValidationError({'product': 'El producto pertenece a otra lavandería.'})

    def save(self, *args, **kwargs):
        # El tenant del inventario SIEMPRE es el del producto: se sincroniza solo.
        if self.product_id:
            self.laundry_id = self.product.laundry_id
        super().save(*args, **kwargs)
