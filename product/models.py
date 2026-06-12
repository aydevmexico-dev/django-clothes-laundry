from django.core.exceptions import ValidationError
from django.db import models

from laundries.models import Laundry, TenantManager


class Category(models.Model):
    laundry = models.ForeignKey(
        Laundry,
        on_delete=models.CASCADE,
        related_name='categories',
        verbose_name='Lavandería',
    )
    name = models.CharField(max_length=100, verbose_name='Nombre de la categoría')

    objects = TenantManager()

    class Meta:
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'
        ordering = ['name']
        constraints = [
            # El nombre es único DENTRO de la lavandería, no globalmente:
            # dos lavanderías distintas pueden tener la categoría "Planchado".
            models.UniqueConstraint(
                fields=['laundry', 'name'],
                name='unique_category_name_per_laundry',
            ),
        ]

    def __str__(self):
        return self.name


class Product(models.Model):
    """
    Elemento del catálogo (concepto/servicio). NO es una transacción: por eso
    ya no lleva folio. El folio vive en el Ticket de venta (app `service`).
    """

    laundry = models.ForeignKey(
        Laundry,
        on_delete=models.CASCADE,
        related_name='products',
        verbose_name='Lavandería',
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='products',
        verbose_name='Categoría',
    )
    name = models.CharField(max_length=100, verbose_name='Nombre del producto')
    description = models.TextField(blank=True, null=True, verbose_name='Descripción')
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Precio')

    objects = TenantManager()

    class Meta:
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['laundry', 'name'],
                name='unique_product_name_per_laundry',
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        # Integridad del aislamiento: la categoría debe pertenecer a la misma
        # lavandería que el producto. Evita "cruzar" datos entre tenants.
        if self.category_id and self.laundry_id and self.category.laundry_id != self.laundry_id:
            raise ValidationError(
                {'category': 'La categoría pertenece a otra lavandería.'}
            )
