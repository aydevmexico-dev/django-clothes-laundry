"""
Tests del módulo de ventas: aislamiento del historial/recibo, blindaje del POS
(productos ajenos, precios manipulados, tickets vacíos, folio del tenant) y
automatización financiera (anticipo, saldo restante, liquidación).
"""
from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from laundries.tests import TwoTenantTestCase

from .models import Ticket, TicketDetail


def pos_data(lines, client='', partial='', delivery=''):
    """Arma el POST del POS con el management form del inline formset."""
    data = {
        'client': client,
        'partial_payment': partial,
        'delivery_date_time': delivery,
        'details-TOTAL_FORMS': str(len(lines)),
        'details-INITIAL_FORMS': '0',
        'details-MIN_NUM_FORMS': '0',
        'details-MAX_NUM_FORMS': '1000',
    }
    for index, (product_id, quantity) in enumerate(lines):
        data[f'details-{index}-product'] = str(product_id)
        data[f'details-{index}-quantity'] = str(quantity)
    return data


class TicketHistoryIsolationTests(TwoTenantTestCase):

    def test_history_shows_only_own_folios(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('service:ticket_list'))
        self.assertContains(response, self.ticket_alpha.folio)
        self.assertNotContains(response, self.ticket_bravo.folio)

    def test_foreign_ticket_pk_is_a_404_not_a_receipt(self):
        # "Adivinar" la PK del ticket rival en la URL del recibo: no existe.
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(
            reverse('service:ticket_detail', kwargs={'pk': self.ticket_bravo.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_own_receipt_renders_frozen_prices(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(
            reverse('service:ticket_detail', kwargs={'pk': self.ticket_alpha.pk})
        )
        self.assertContains(response, self.ticket_alpha.folio)
        self.assertContains(response, 'Carga sencilla ALPHA')


class PosCreateTests(TwoTenantTestCase):

    def test_sale_generates_tenant_folio_and_server_side_total(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.post(
            reverse('service:ticket_create'),
            pos_data([(self.product_alpha.pk, 3)], client=self.client_alpha.pk),
        )
        ticket = Ticket.objects.for_laundry(self.alpha).latest('created_at')
        self.assertRedirects(
            response, reverse('service:ticket_detail', kwargs={'pk': ticket.pk})
        )
        self.assertTrue(ticket.folio.startswith('ALP'))         # prefijo del tenant
        self.assertEqual(ticket.total, Decimal('240.00'))       # 3 × $80 del catálogo

    def test_foreign_product_is_an_invalid_choice_not_a_sale(self):
        self.client.force_login(self.cashier_alpha)
        before = Ticket.objects.count()
        response = self.client.post(
            reverse('service:ticket_create'),
            pos_data([(self.product_bravo.pk, 1)]),             # producto del rival
        )
        self.assertEqual(response.status_code, 200)             # re-pinta con error
        self.assertEqual(Ticket.objects.count(), before)        # no se vendió nada

    def test_foreign_client_is_an_invalid_choice(self):
        self.client.force_login(self.cashier_alpha)
        before = Ticket.objects.count()
        response = self.client.post(
            reverse('service:ticket_create'),
            pos_data([(self.product_alpha.pk, 1)], client=self.client_bravo.pk),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Ticket.objects.count(), before)

    def test_tampered_price_in_post_is_ignored(self):
        # El POS nunca manda precio; si alguien lo inyecta, el backend lo ignora
        # y congela el del catálogo.
        self.client.force_login(self.cashier_alpha)
        data = pos_data([(self.product_alpha.pk, 1)])
        data['details-0-unit_price'] = '0.01'
        data['total'] = '0.01'
        self.client.post(reverse('service:ticket_create'), data)
        ticket = Ticket.objects.for_laundry(self.alpha).latest('created_at')
        self.assertEqual(ticket.total, Decimal('80.00'))

    def test_empty_ticket_is_rejected(self):
        self.client.force_login(self.cashier_alpha)
        before = Ticket.objects.count()
        response = self.client.post(reverse('service:ticket_create'), pos_data([]))
        self.assertContains(response, 'Agrega al menos un producto')
        self.assertEqual(Ticket.objects.count(), before)

    def test_pos_catalog_only_offers_own_products(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('service:ticket_create'))
        self.assertContains(response, 'Carga sencilla ALPHA')
        self.assertNotContains(response, 'Planchado fino BRAVO')

    def test_member_without_add_ticket_cannot_open_pos(self):
        self.client.force_login(self.member_no_perms)
        response = self.client.get(reverse('service:ticket_create'))
        self.assertEqual(response.status_code, 403)


class PosAbuseBoundsTests(TwoTenantTestCase):
    """Límites duros del POS: cantidades absurdas y POSTs inflados a mano."""

    def test_absurd_quantity_is_rejected_not_a_500(self):
        # Sin tope, 99 999 999 999 × $80 desbordaría el DecimalField del
        # subtotal y la petición moriría con un error de base de datos.
        self.client.force_login(self.cashier_alpha)
        before = Ticket.objects.count()
        response = self.client.post(
            reverse('service:ticket_create'),
            pos_data([(self.product_alpha.pk, 99_999_999_999)]),
        )
        self.assertEqual(response.status_code, 200)     # error de form, no 500
        self.assertEqual(Ticket.objects.count(), before)

    def test_zero_and_negative_quantities_are_rejected(self):
        self.client.force_login(self.cashier_alpha)
        before = Ticket.objects.count()
        for quantity in (0, -3):
            response = self.client.post(
                reverse('service:ticket_create'),
                pos_data([(self.product_alpha.pk, quantity)]),
            )
            self.assertEqual(response.status_code, 200, quantity)
        self.assertEqual(Ticket.objects.count(), before)

    def test_inflated_formset_beyond_max_num_is_rejected(self):
        self.client.force_login(self.cashier_alpha)
        before = Ticket.objects.count()
        lines = [(self.product_alpha.pk, 1)] * 201      # supera max_num=200
        response = self.client.post(reverse('service:ticket_create'), pos_data(lines))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Ticket.objects.count(), before)


class PaymentAutomationModelTests(TwoTenantTestCase):
    """El modelo deriva saldo restante y estatus de pago sin intervención."""

    def _ticket(self, partial=Decimal('0')):
        ticket = Ticket.objects.create(
            laundry=self.alpha, client=self.client_alpha, partial_payment=partial
        )
        TicketDetail.objects.create(
            ticket=ticket, product=self.product_alpha, quantity=2   # total $160
        )
        ticket.refresh_from_db()
        return ticket

    def test_partial_below_total_leaves_balance_and_unpaid(self):
        ticket = self._ticket(partial=Decimal('60.00'))
        self.assertEqual(ticket.total, Decimal('160.00'))
        self.assertEqual(ticket.remaining_balance, Decimal('100.00'))
        self.assertFalse(ticket.paid)

    def test_partial_equal_to_total_marks_paid(self):
        ticket = self._ticket(partial=Decimal('160.00'))
        self.assertEqual(ticket.remaining_balance, Decimal('0.00'))
        self.assertTrue(ticket.paid)

    def test_balance_is_never_negative_even_if_overpaid(self):
        # Fail-safe de modelo: aunque un flujo externo registre un anticipo
        # mayor al total, el saldo queda acotado en 0 (y el ticket, pagado).
        ticket = self._ticket(partial=Decimal('500.00'))
        self.assertEqual(ticket.remaining_balance, Decimal('0.00'))
        self.assertTrue(ticket.paid)

    def test_new_ticket_without_lines_is_not_paid(self):
        empty = Ticket.objects.create(laundry=self.alpha)
        self.assertFalse(empty.paid)                    # total 0 no es "pagado"
        self.assertEqual(empty.remaining_balance, Decimal('0.00'))

    def test_adding_lines_recalculates_balance_via_signals(self):
        from product.models import Product

        ticket = self._ticket(partial=Decimal('160.00'))
        self.assertTrue(ticket.paid)

        # Llega una prenda más: el total sube y el ticket DEJA de estar pagado.
        extra = Product.objects.create(
            laundry=self.alpha, category=self.cat_alpha,
            name='Edredón ALPHA', price=Decimal('120.00'),
        )
        TicketDetail.objects.create(ticket=ticket, product=extra, quantity=1)
        ticket.refresh_from_db()
        self.assertFalse(ticket.paid)
        self.assertEqual(ticket.remaining_balance, Decimal('120.00'))

    def test_is_overdue_only_when_late_and_unpaid(self):
        late = self._ticket()
        Ticket.objects.filter(pk=late.pk).update(
            delivery_date_time=timezone.now() - timedelta(hours=3)
        )
        late.refresh_from_db()
        self.assertTrue(late.is_overdue)

        settled = self._ticket(partial=Decimal('160.00'))
        Ticket.objects.filter(pk=settled.pk).update(
            delivery_date_time=timezone.now() - timedelta(hours=3)
        )
        settled.refresh_from_db()
        self.assertFalse(settled.is_overdue)            # pagado nunca está atrasado

        future = self._ticket()
        Ticket.objects.filter(pk=future.pk).update(
            delivery_date_time=timezone.now() + timedelta(hours=3)
        )
        future.refresh_from_db()
        self.assertFalse(future.is_overdue)


class PosPaymentFlowTests(TwoTenantTestCase):
    """El POS captura anticipo y entrega; el backend deriva todo lo demás."""

    def test_sale_with_advance_keeps_balance_open(self):
        self.client.force_login(self.cashier_alpha)
        delivery = (timezone.localtime() + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')
        response = self.client.post(
            reverse('service:ticket_create'),
            pos_data([(self.product_alpha.pk, 3)], partial='100.00', delivery=delivery),
        )
        ticket = Ticket.objects.for_laundry(self.alpha).latest('created_at')
        self.assertRedirects(
            response, reverse('service:ticket_detail', kwargs={'pk': ticket.pk})
        )
        self.assertEqual(ticket.total, Decimal('240.00'))
        self.assertEqual(ticket.partial_payment, Decimal('100.00'))
        self.assertEqual(ticket.remaining_balance, Decimal('140.00'))
        self.assertFalse(ticket.paid)
        self.assertIsNotNone(ticket.delivery_date_time)

    def test_full_advance_marks_ticket_paid(self):
        self.client.force_login(self.cashier_alpha)
        self.client.post(
            reverse('service:ticket_create'),
            pos_data([(self.product_alpha.pk, 2)], partial='160.00'),
        )
        ticket = Ticket.objects.for_laundry(self.alpha).latest('created_at')
        self.assertTrue(ticket.paid)
        self.assertEqual(ticket.remaining_balance, Decimal('0.00'))

    def test_advance_above_total_is_rejected_without_consuming_folio(self):
        self.client.force_login(self.cashier_alpha)
        self.alpha.refresh_from_db()
        counter_before = self.alpha.folio_counter
        tickets_before = Ticket.objects.count()

        response = self.client.post(
            reverse('service:ticket_create'),
            pos_data([(self.product_alpha.pk, 1)], partial='500.00'),   # total $80
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'no puede ser mayor que el total')
        self.assertEqual(Ticket.objects.count(), tickets_before)
        self.alpha.refresh_from_db()
        # La secuencia de folios NO se gastó en el intento fallido.
        self.assertEqual(self.alpha.folio_counter, counter_before)

    def test_negative_advance_is_rejected(self):
        self.client.force_login(self.cashier_alpha)
        before = Ticket.objects.count()
        response = self.client.post(
            reverse('service:ticket_create'),
            pos_data([(self.product_alpha.pk, 1)], partial='-50'),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Ticket.objects.count(), before)

    def test_delivery_and_advance_are_optional(self):
        self.client.force_login(self.cashier_alpha)
        self.client.post(
            reverse('service:ticket_create'), pos_data([(self.product_alpha.pk, 1)])
        )
        ticket = Ticket.objects.for_laundry(self.alpha).latest('created_at')
        self.assertIsNone(ticket.delivery_date_time)
        self.assertEqual(ticket.partial_payment, Decimal('0'))
        self.assertEqual(ticket.remaining_balance, Decimal('80.00'))


class TicketSettleTests(TwoTenantTestCase):
    """Liquidación del saldo al entregar: permisos, aislamiento y efecto."""

    def test_cashier_settles_own_ticket(self):
        self.client.force_login(self.cashier_alpha)
        self.assertFalse(self.ticket_alpha.paid)
        response = self.client.post(
            reverse('service:ticket_settle', kwargs={'pk': self.ticket_alpha.pk})
        )
        self.assertRedirects(
            response,
            reverse('service:ticket_detail', kwargs={'pk': self.ticket_alpha.pk}),
        )
        self.ticket_alpha.refresh_from_db()
        self.assertTrue(self.ticket_alpha.paid)
        self.assertEqual(self.ticket_alpha.remaining_balance, Decimal('0.00'))
        self.assertEqual(self.ticket_alpha.partial_payment, self.ticket_alpha.total)

    def test_settling_foreign_ticket_is_404(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.post(
            reverse('service:ticket_settle', kwargs={'pk': self.ticket_bravo.pk})
        )
        self.assertEqual(response.status_code, 404)
        self.ticket_bravo.refresh_from_db()
        self.assertFalse(self.ticket_bravo.paid)

    def test_settle_requires_post(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(
            reverse('service:ticket_settle', kwargs={'pk': self.ticket_alpha.pk})
        )
        self.assertEqual(response.status_code, 405)

    def test_member_without_change_perm_cannot_settle(self):
        self.client.force_login(self.member_no_perms)
        response = self.client.post(
            reverse('service:ticket_settle', kwargs={'pk': self.ticket_alpha.pk})
        )
        self.assertEqual(response.status_code, 403)
