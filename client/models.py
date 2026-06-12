from django.db import models

from laundries.models import Laundry, TenantManager


class Client(models.Model):
    laundry = models.ForeignKey(
        Laundry,
        on_delete=models.CASCADE,
        related_name='clients',
        verbose_name='Lavandería',
    )
    name = models.CharField(max_length=100, verbose_name='Nombre del cliente')
    email = models.EmailField(blank=True, null=True, verbose_name='Correo electrónico')
    phone_number = models.CharField(
        max_length=10, blank=True, null=True, verbose_name='Número de teléfono'
    )
    address = models.TextField(blank=True, null=True, verbose_name='Dirección')
    rfc = models.CharField(max_length=13, blank=True, null=True, verbose_name='RFC')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de alta')

    objects = TenantManager()

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        ordering = ['name']
        constraints = [
            # El RFC sí es único POR lavandería (la condición evita que varios
            # NULL colisionen entre sí). El email, en cambio, NO lleva ninguna
            # restricción de unicidad: por regla de negocio, varios clientes de
            # una misma sucursal (p. ej. una familia) pueden compartir correo.
            models.UniqueConstraint(
                fields=['laundry', 'rfc'],
                name='unique_client_rfc_per_laundry',
                condition=models.Q(rfc__isnull=False),
            ),
        ]

    def __str__(self):
        return self.name
