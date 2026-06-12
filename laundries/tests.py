"""
Tests de navegación y aislamiento multi-tenant del frontend.

Estrategia: se montan DOS lavanderías rivales con catálogos, clientes y ventas
de nombres inconfundibles ("…ALPHA" / "…BRAVO"). Cada test verifica dos cosas:
  1) que el usuario de Alpha SÍ ve lo suyo, y
  2) que en el MISMO HTML no aparece ni un byte de Bravo.
Como el tenant nunca viaja en la URL, no hay "ID que adivinar": los tests de
acceso cruzado piden recursos de Bravo por PK y esperan 404/403, jamás datos.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from client.models import Client
from inventory.models import Inventory
from product.models import Category, Product
from service.models import Ticket, TicketDetail

from .models import Laundry, LaundryStaff

User = get_user_model()


class TwoTenantTestCase(TestCase):
    """
    Fixture compartido: dos lavanderías completas y todos los perfiles de
    usuario relevantes. Lo heredan los tests de cada app.
    """

    @classmethod
    def setUpTestData(cls):
        # ----- Tenants ----------------------------------------------------
        cls.alpha = Laundry.objects.create(name='Lavandería Alpha', prefix='ALP')
        cls.bravo = Laundry.objects.create(name='Lavandería Bravo', prefix='BRV')

        # ----- Usuarios (los grupos los creó la migración 0003) ----------
        cashiers = Group.objects.get(name='Cajeros')
        tenant_admins = Group.objects.get(name='Administradores de lavandería')

        cls.cashier_alpha = User.objects.create_user('caja.alpha', password='x')
        cls.cashier_alpha.groups.add(cashiers)
        LaundryStaff.objects.create(user=cls.cashier_alpha, laundry=cls.alpha)

        cls.admin_alpha = User.objects.create_user('admin.alpha', password='x')
        cls.admin_alpha.groups.add(tenant_admins)
        LaundryStaff.objects.create(
            user=cls.admin_alpha, laundry=cls.alpha, is_tenant_admin=True
        )

        cls.cashier_bravo = User.objects.create_user('caja.bravo', password='x')
        cls.cashier_bravo.groups.add(cashiers)
        LaundryStaff.objects.create(user=cls.cashier_bravo, laundry=cls.bravo)

        # Miembro del tenant pero SIN permisos de modelo (sin grupo).
        cls.member_no_perms = User.objects.create_user('sin.permisos', password='x')
        LaundryStaff.objects.create(user=cls.member_no_perms, laundry=cls.alpha)

        # Usuario autenticado SIN lavandería asignada (huérfano).
        cls.orphan = User.objects.create_user('huerfano', password='x')

        cls.superuser = User.objects.create_superuser('root', password='x')

        # ----- Catálogo, clientes e inventario por tenant ------------------
        cls.cat_alpha = Category.objects.create(laundry=cls.alpha, name='Lavado ALPHA')
        cls.product_alpha = Product.objects.create(
            laundry=cls.alpha, category=cls.cat_alpha,
            name='Carga sencilla ALPHA', price=Decimal('80.00'),
        )
        cls.cat_bravo = Category.objects.create(laundry=cls.bravo, name='Planchado BRAVO')
        cls.product_bravo = Product.objects.create(
            laundry=cls.bravo, category=cls.cat_bravo,
            name='Planchado fino BRAVO', price=Decimal('55.00'),
        )

        cls.client_alpha = Client.objects.create(laundry=cls.alpha, name='María de ALPHA')
        cls.client_bravo = Client.objects.create(laundry=cls.bravo, name='Bruno de BRAVO')

        Inventory.objects.create(product=cls.product_alpha, quantity=2)   # stock crítico

        # ----- Ventas: una por tenant --------------------------------------
        cls.ticket_alpha = Ticket.objects.create(laundry=cls.alpha, client=cls.client_alpha)
        TicketDetail.objects.create(
            ticket=cls.ticket_alpha, product=cls.product_alpha, quantity=2
        )
        cls.ticket_bravo = Ticket.objects.create(laundry=cls.bravo, client=cls.client_bravo)
        TicketDetail.objects.create(
            ticket=cls.ticket_bravo, product=cls.product_bravo, quantity=1
        )


class DashboardAccessTests(TwoTenantTestCase):
    """Quién puede entrar al panel y a dónde se redirige a quien no."""

    def test_anonymous_redirects_to_login_with_next(self):
        response = self.client.get(reverse('panel:dashboard'))
        self.assertRedirects(response, '/?next=/panel/')

    def test_orphan_user_gets_403(self):
        self.client.force_login(self.orphan)
        response = self.client.get(reverse('panel:dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_superuser_without_membership_goes_to_admin(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('panel:dashboard'))
        self.assertRedirects(response, reverse('admin:index'))

    def test_inactive_laundry_locks_out_its_staff(self):
        Laundry.objects.filter(pk=self.alpha.pk).update(is_active=False)
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('panel:dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_login_redirects_to_dashboard(self):
        response = self.client.post(
            '/', {'username': 'caja.alpha', 'password': 'x'}, follow=True
        )
        self.assertEqual(response.request['PATH_INFO'], '/panel/')


class DashboardIsolationTests(TwoTenantTestCase):
    """Ni una métrica, nombre o folio del otro tenant en el HTML del panel."""

    def test_dashboard_shows_only_own_tenant_data(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('panel:dashboard'))

        self.assertContains(response, 'Lavandería Alpha')
        self.assertContains(response, self.ticket_alpha.folio)     # último ticket propio
        self.assertContains(response, 'Carga sencilla ALPHA')      # stock crítico propio

        self.assertNotContains(response, 'Lavandería Bravo')
        self.assertNotContains(response, 'BRAVO')                  # nada del rival
        self.assertNotContains(response, self.ticket_bravo.folio)

    def test_chart_payload_only_aggregates_own_tenant(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('panel:dashboard'))
        payload = response.context['chart_payload']

        # Hoy se vendieron 2 × $80 en Alpha; la venta de Bravo ($55) NO suma.
        self.assertEqual(payload['salesSeries']['values'][-1], 160.0)
        self.assertEqual(payload['topCategories']['labels'], ['Lavado ALPHA'])

    def test_kpis_count_only_own_tenant(self):
        self.client.force_login(self.cashier_bravo)
        response = self.client.get(reverse('panel:dashboard'))
        kpis = response.context['kpis']

        self.assertEqual(kpis['tickets_today'], 1)
        self.assertEqual(float(kpis['sales_today']), 55.0)
        self.assertEqual(kpis['clients_total'], 1)
        self.assertEqual(kpis['low_stock'], 0)     # el stock crítico es de Alpha

    def test_financial_kpis_are_tenant_scoped(self):
        # Alpha tiene $160 en anaquel; Bravo $55. Ninguno ve el del otro.
        self.client.force_login(self.cashier_alpha)
        kpis = self.client.get(reverse('panel:dashboard')).context['kpis']
        self.assertEqual(float(kpis['receivable']), 160.0)
        self.assertEqual(kpis['pending_count'], 1)
        self.assertEqual(float(kpis['collected']), 0.0)

        self.client.force_login(self.cashier_bravo)
        kpis = self.client.get(reverse('panel:dashboard')).context['kpis']
        self.assertEqual(float(kpis['receivable']), 55.0)

    def test_income_chart_payload_reflects_settlement(self):
        # Al liquidar el ticket de Alpha, la dona pasa de todo-pendiente a
        # todo-cobrado, sin que la venta de Bravo contamine los números.
        self.client.force_login(self.cashier_alpha)
        payload = self.client.get(reverse('panel:dashboard')).context['chart_payload']
        self.assertEqual(payload['incomeStatus']['values'], [0.0, 160.0])

        self.client.post(
            reverse('service:ticket_settle', kwargs={'pk': self.ticket_alpha.pk})
        )
        payload = self.client.get(reverse('panel:dashboard')).context['chart_payload']
        self.assertEqual(payload['incomeStatus']['values'], [160.0, 0.0])

        kpis = self.client.get(reverse('panel:dashboard')).context['kpis']
        self.assertEqual(kpis['collected_pct'], 100)

    def test_deliveries_today_counts_only_pending_of_today(self):
        from django.utils import timezone
        from service.models import Ticket

        # La hora se fija en horario LOCAL: a las 23:00 locales, now() en UTC
        # ya es "mañana" y el conteo de hoy no la incluiría.
        Ticket.objects.filter(pk=self.ticket_alpha.pk).update(
            delivery_date_time=timezone.localtime().replace(
                hour=18, minute=0, second=0, microsecond=0
            )
        )
        self.client.force_login(self.cashier_alpha)
        kpis = self.client.get(reverse('panel:dashboard')).context['kpis']
        self.assertEqual(kpis['deliveries_today'], 1)

        # La entrega de hoy de BRAVO no aparece en el panel de Alpha.
        self.client.force_login(self.cashier_bravo)
        kpis = self.client.get(reverse('panel:dashboard')).context['kpis']
        self.assertEqual(kpis['deliveries_today'], 0)


class DashboardFilterTests(TwoTenantTestCase):
    """Filtros combinables del panel y botón «Eliminar filtros»."""

    def _make_old_ticket(self, days_ago=40):
        """Ticket de Alpha con $80 pendientes, fechado `days_ago` días atrás."""
        old = Ticket.objects.create(laundry=self.alpha, client=self.client_alpha)
        TicketDetail.objects.create(ticket=old, product=self.product_alpha, quantity=1)
        Ticket.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
        return old

    def test_default_is_full_history_with_no_active_filters(self):
        self._make_old_ticket()
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('panel:dashboard'))
        self.assertFalse(response.context['filters']['active'])
        # Sin filtros, lo financiero abarca TODO el histórico: $160 + $80.
        self.assertEqual(float(response.context['kpis']['receivable']), 240.0)
        self.assertContains(response, 'Eliminar filtros')

    def test_date_range_filter_limits_universe(self):
        self._make_old_ticket()
        self.client.force_login(self.cashier_alpha)
        today = timezone.localdate()
        response = self.client.get(reverse('panel:dashboard'), {
            'fecha_inicio': (today - timedelta(days=7)).isoformat(),
            'fecha_fin': today.isoformat(),
        })
        context = response.context
        self.assertTrue(context['filters']['active'])
        self.assertEqual(float(context['kpis']['receivable']), 160.0)   # sin el viejo
        self.assertEqual(float(context['kpis']['sales_today']), 160.0)  # venta del periodo

    def test_client_filter_combines_with_period(self):
        other = Client.objects.create(laundry=self.alpha, name='Otro Cliente ALPHA')
        ticket = Ticket.objects.create(laundry=self.alpha, client=other)
        TicketDetail.objects.create(ticket=ticket, product=self.product_alpha, quantity=1)

        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('panel:dashboard'), {
            'cliente': self.client_alpha.pk,
            'periodo': 'mes',
        })
        # Solo las ventas de María ($160); las de «Otro Cliente» quedan fuera.
        self.assertEqual(float(response.context['kpis']['sales_today']), 160.0)

    def test_foreign_client_id_is_ignored_not_leaked(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(
            reverse('panel:dashboard'), {'cliente': self.client_bravo.pk}
        )
        # El ID ajeno no existe dentro del tenant: se ignora sin filtrar nada,
        # y por supuesto ni el nombre ni los datos de Bravo aparecen.
        self.assertFalse(response.context['filters']['active'])
        self.assertNotContains(response, 'BRAVO')

    def test_invalid_dates_are_ignored_without_error(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('panel:dashboard'), {
            'fecha_inicio': 'basura', 'fecha_fin': '2026-13-99',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['filters']['active'])

    def test_inverted_dates_are_swapped(self):
        self.client.force_login(self.cashier_alpha)
        today = timezone.localdate()
        response = self.client.get(reverse('panel:dashboard'), {
            'fecha_inicio': today.isoformat(),
            'fecha_fin': (today - timedelta(days=5)).isoformat(),
        })
        filters = response.context['filters']
        self.assertLess(filters['date_start'], filters['date_end'])

    def test_predefined_period_overrides_manual_dates(self):
        self._make_old_ticket()
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('panel:dashboard'), {
            'periodo': 'mes',
            'fecha_inicio': '2020-01-01',       # el periodo predefinido manda
        })
        filters = response.context['filters']
        self.assertEqual(filters['date_start'], timezone.localdate().replace(day=1))
        self.assertEqual(float(response.context['kpis']['receivable']), 160.0)

    def test_reset_is_a_clean_anchor_to_base_url(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('panel:dashboard'), {'periodo': 'mes'})
        # Enlace simple a la URL base, sin QueryString: el reset del brief.
        self.assertContains(response, f'href="{reverse("panel:dashboard")}"')
        self.assertContains(response, 'Eliminar filtros')

    def test_sales_series_respects_filtered_range(self):
        self._make_old_ticket()
        self.client.force_login(self.cashier_alpha)
        today = timezone.localdate()
        response = self.client.get(reverse('panel:dashboard'), {
            'fecha_inicio': (today - timedelta(days=2)).isoformat(),
            'fecha_fin': today.isoformat(),
        })
        series = response.context['chart_payload']['salesSeries']
        self.assertEqual(len(series['values']), 3)          # exactamente 3 días
        self.assertEqual(series['values'][-1], 160.0)

    def test_long_ranges_group_the_series_by_month(self):
        self._make_old_ticket(days_ago=100)
        self.client.force_login(self.cashier_alpha)
        today = timezone.localdate()
        response = self.client.get(reverse('panel:dashboard'), {
            'fecha_inicio': (today - timedelta(days=120)).isoformat(),
            'fecha_fin': today.isoformat(),
        })
        series = response.context['chart_payload']['salesSeries']
        self.assertLessEqual(len(series['labels']), 6)      # meses, no 121 barras
        self.assertEqual(sum(series['values']), 240.0)      # viejo + hoy, nada más


class NavigationPermissionTests(TwoTenantTestCase):
    """El menú lateral refleja los permisos reales del backend."""

    def test_cashier_sees_operation_but_not_catalog_management(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('panel:dashboard'))
        self.assertContains(response, 'Nueva venta')
        self.assertContains(response, 'Clientes')
        # En el catálogo, el cajero consulta pero no ve acciones de gestión.
        catalog = self.client.get(reverse('product:list'))
        self.assertNotContains(catalog, 'Nuevo producto')
        self.assertNotContains(catalog, 'Nueva categoría')

    def test_tenant_admin_sees_catalog_management(self):
        self.client.force_login(self.admin_alpha)
        # El rol se refleja en el sidebar…
        response = self.client.get(reverse('panel:dashboard'))
        self.assertContains(response, 'Administración')
        # …y en las acciones de gestión del catálogo (permisos reales).
        catalog = self.client.get(reverse('product:list'))
        self.assertContains(catalog, 'Nuevo producto')
        self.assertContains(catalog, 'Nueva categoría')

    def test_member_without_perms_sees_bare_menu_and_cannot_enter_modules(self):
        self.client.force_login(self.member_no_perms)
        response = self.client.get(reverse('panel:dashboard'))
        self.assertNotContains(response, 'Nueva venta')   # sin add_ticket no se ofrece

        for url_name in ('product:list', 'client:list', 'service:ticket_list'):
            denied = self.client.get(reverse(url_name))
            self.assertEqual(denied.status_code, 403, url_name)

    def test_sidebar_identifies_user_and_laundry(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('panel:dashboard'))
        self.assertContains(response, 'caja.alpha')
        self.assertContains(response, self.alpha.prefix)
