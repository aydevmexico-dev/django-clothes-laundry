from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from client.models import Client
from laundries.models import Laundry, TenantManager
from product.models import Product


class Ticket(models.Model):
    """
    Transacción de venta. ES quien genera el folio único por lavandería
    (consumiendo el `folio_counter` del tenant) y agrupa varios productos.
    """

    laundry = models.ForeignKey(
        Laundry,
        on_delete=models.CASCADE,
        related_name='tickets',
        verbose_name='Lavandería',
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name='tickets',
        null=True,
        blank=True,
        verbose_name='Cliente',
    )
    folio = models.CharField(
        max_length=20,
        editable=False,
        verbose_name='Folio de venta',
        help_text='Se genera al guardar: prefijo de la lavandería + 15 dígitos.',
    )
    folio_number = models.PositiveBigIntegerField(
        null=True,
        editable=False,
        verbose_name='Consecutivo del folio',
    )
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Total',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de venta')
    delivery_date_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha y hora de entrega',
        help_text='Fecha y hora estimada de entrega al cliente; opcional.',
    )

    partial_payment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Pago parcial',
        help_text='Anticipo que deja el cliente; opcional.',
    )
    remaining_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        editable=False,   # SIEMPRE derivado: total - anticipo, nunca capturado a mano
        verbose_name='Saldo restante',
        help_text='Se calcula solo: total menos el pago parcial. Nunca es negativo.',
    )
    paid = models.BooleanField(
        default=False,
        editable=False,   # derivado: True cuando el saldo llega a cero
        verbose_name='¿Pagado?',
    )

    objects = TenantManager()

    class Meta:
        verbose_name = 'Ticket de venta'
        verbose_name_plural = 'Tickets de venta'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['laundry', 'folio'],
                name='unique_ticket_folio_per_laundry',
            ),
        ]

    def __str__(self):
        return self.folio or f'Ticket #{self.pk}'

    def save(self, *args, **kwargs):
        # El estado financiero se deriva SIEMPRE antes de tocar la base de
        # datos: ningún flujo (POS, admin, shell) puede guardar un saldo o un
        # `paid` inconsistentes con el total y el anticipo.
        self._sync_payment_status()
        if not self.folio:
            self._assign_folio_and_save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    def _assign_folio_and_save(self, *args, **kwargs):
        """
        Toma el folio de forma atómica y a prueba de concurrencia.

        select_for_update() bloquea la fila de la lavandería: si dos cajas
        registran una venta a la vez, la segunda espera a que la primera libere
        el lock, de modo que cada ticket obtiene un consecutivo distinto y la
        secuencia del tenant jamás se duplica ni se rompe.
        """
        with transaction.atomic():
            laundry = (
                Laundry.objects
                .select_for_update()
                .get(pk=self.laundry_id)
            )
            next_number = laundry.folio_counter + 1        # contador actual + 1
            laundry.folio_counter = next_number            # se persiste el incremento
            laundry.save(update_fields=['folio_counter'])

            self.folio_number = next_number
            # prefix del tenant + 15 dígitos con ceros a la izquierda -> LVA000000000000001
            self.folio = f'{laundry.prefix}{next_number:015d}'
            super().save(*args, **kwargs)

    def _sync_payment_status(self):
        """
        Deriva el estado financiero del ticket. Reglas:

          * El anticipo nunca es negativo (fail-safe de modelo; el formulario
            del POS además lo valida con mensaje).
          * Saldo restante = total − anticipo, acotado en 0: aunque alguien
            registre un anticipo mayor al total, el saldo JAMÁS queda negativo.
          * `paid` solo es True cuando hay venta real (total > 0) y el saldo
            llegó a cero; un ticket recién creado sin líneas no cuenta como
            pagado.
        """
        self.partial_payment = max(self.partial_payment or 0, 0)
        self.remaining_balance = max((self.total or 0) - self.partial_payment, 0)
        self.paid = bool(self.total) and self.remaining_balance == 0

    def recalculate_total(self, save=True):
        """Recalcula total, saldo restante y estatus de pago desde el detalle."""
        self.total = self.details.aggregate(t=Sum('subtotal'))['t'] or 0
        self._sync_payment_status()
        if save:
            super().save(
                update_fields=['total', 'partial_payment', 'remaining_balance', 'paid']
            )
        return self.total

    # ------------------- Estado operativo (solo lectura) -----------------
    @property
    def is_overdue(self):
        """La entrega prometida ya pasó y el ticket sigue sin liquidarse."""
        return (
            not self.paid
            and self.delivery_date_time is not None
            and self.delivery_date_time < timezone.now()
        )


class TicketDetail(models.Model):
    """
    Línea de venta: tabla intermedia entre Ticket y Product que añade la
    cantidad y CONGELA el precio histórico al momento de la venta.
    """

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name='details',
        verbose_name='Ticket',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='ticket_details',
        verbose_name='Producto',
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name='Cantidad')
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Precio unitario (congelado)',
        help_text='Precio del producto al momento de la venta; no cambia aunque el catálogo cambie.',
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        editable=False,
        verbose_name='Subtotal',
    )

    class Meta:
        verbose_name = 'Detalle de venta'
        verbose_name_plural = 'Detalles de venta'
        constraints = [
            # Un mismo producto no se repite como línea suelta dentro del ticket:
            # se ajusta su cantidad.
            models.UniqueConstraint(
                fields=['ticket', 'product'],
                name='unique_product_per_ticket',
            ),
        ]

    def __str__(self):
        return f'{self.quantity} × {self.product.name}'

    def clean(self):
        # El producto vendido debe pertenecer a la misma lavandería del ticket.
        if self.product_id and self.ticket_id and self.product.laundry_id != self.ticket.laundry_id:
            raise ValidationError(
                {'product': 'El producto pertenece a otra lavandería.'}
            )

    def save(self, *args, **kwargs):
        # El precio se HEREDA del catálogo y se CONGELA al crear la línea.
        # `self._state.adding` es True solo en el alta: así el cajero nunca teclea
        # el precio, y una edición posterior (p. ej. cambiar la cantidad) NO lo
        # recalcula, preservando el valor histórico aunque el catálogo cambie.
        # `self.product` ya está cargado en memoria (lo asignó el form/llamador),
        # por lo que `self.product.price` no dispara una consulta extra.
        if self._state.adding and self.product_id:
            self.unit_price = self.product.price
        self.subtotal = (self.unit_price or 0) * self.quantity
        super().save(*args, **kwargs)
