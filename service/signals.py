"""
Mantiene `Ticket.total` sincronizado con sus líneas de detalle.

Al guardarse o borrarse cualquier `TicketDetail`, se recalcula el total del
ticket sumando los subtotales vigentes. Vive en señales (no en el admin) para
que funcione igual desde el panel, el shell o una API.
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Ticket, TicketDetail


@receiver(post_save, sender=TicketDetail)
def recalc_total_on_detail_save(sender, instance, **kwargs):
    # `instance.ticket` ya está en memoria (FK asignada al crear/editar la línea).
    instance.ticket.recalculate_total()


@receiver(post_delete, sender=TicketDetail)
def recalc_total_on_detail_delete(sender, instance, **kwargs):
    # Si el ticket se está eliminando en cascada, su fila ya no existe:
    # filtramos para no intentar guardar un ticket borrado.
    ticket = Ticket.objects.filter(pk=instance.ticket_id).first()
    if ticket is not None:
        ticket.recalculate_total()
