"""Aislamiento del catálogo de productos en el frontend (consulta y CRUD)."""
from decimal import Decimal

from django.urls import reverse

from laundries.tests import TwoTenantTestCase

from .models import Category, Product


class ProductListIsolationTests(TwoTenantTestCase):

    def test_list_shows_only_own_catalog(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('product:list'))
        self.assertContains(response, 'Carga sencilla ALPHA')
        self.assertContains(response, 'Lavado ALPHA')          # chip de categoría propia
        self.assertNotContains(response, 'Planchado fino BRAVO')
        self.assertNotContains(response, 'Planchado BRAVO')    # ni sus categorías

    def test_search_stays_inside_tenant(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('product:list'), {'q': 'Planchado fino'})
        self.assertNotContains(response, 'Planchado fino BRAVO')
        self.assertContains(response, 'Sin resultados')

    def test_filtering_by_foreign_category_returns_empty_not_leak(self):
        # Adivinar el ID de una categoría ajena no filtra hacia sus productos.
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(
            reverse('product:list'), {'categoria': self.cat_bravo.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'BRAVO')
        self.assertEqual(len(response.context['products']), 0)

    def test_stock_column_uses_own_inventory(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('product:list'))
        # El producto Alpha llega a la plantilla con sus 2 piezas de inventario.
        product = response.context['products'][0]
        self.assertEqual(product.inventory.quantity, 2)


class ProductCrudTests(TwoTenantTestCase):
    """Alta y edición de productos: tenant automático, 404 ajeno, permisos."""

    def _product_payload(self, **overrides):
        payload = {
            'category': self.cat_alpha.pk,
            'name': 'Tintorería de saco',
            'description': '',
            'price': '95.50',
        }
        payload.update(overrides)
        return payload

    def test_create_assigns_session_tenant_automatically(self):
        self.client.force_login(self.admin_alpha)
        response = self.client.post(reverse('product:create'), self._product_payload())
        self.assertRedirects(response, reverse('product:list'))
        created = Product.objects.get(name='Tintorería de saco')
        self.assertEqual(created.laundry, self.alpha)       # tenant de la SESIÓN

    def test_laundry_field_in_post_is_ignored(self):
        # Intento de sembrar el producto en el tenant rival manipulando el POST.
        self.client.force_login(self.admin_alpha)
        self.client.post(
            reverse('product:create'),
            self._product_payload(name='Inyectado', laundry=self.bravo.pk),
        )
        self.assertEqual(Product.objects.get(name='Inyectado').laundry, self.alpha)

    def test_category_select_only_offers_own_categories(self):
        self.client.force_login(self.admin_alpha)
        response = self.client.get(reverse('product:create'))
        choices = response.context['form'].fields['category'].queryset
        self.assertIn(self.cat_alpha, choices)
        self.assertNotIn(self.cat_bravo, choices)

    def test_foreign_category_in_post_is_invalid_choice(self):
        self.client.force_login(self.admin_alpha)
        response = self.client.post(
            reverse('product:create'),
            self._product_payload(category=self.cat_bravo.pk),
        )
        self.assertEqual(response.status_code, 200)         # se re-pinta con error
        self.assertFalse(Product.objects.filter(name='Tintorería de saco').exists())

    def test_editing_foreign_product_is_404(self):
        self.client.force_login(self.admin_alpha)
        response = self.client.get(
            reverse('product:update', kwargs={'pk': self.product_bravo.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_update_changes_price_and_redirects_to_list(self):
        self.client.force_login(self.admin_alpha)
        response = self.client.post(
            reverse('product:update', kwargs={'pk': self.product_alpha.pk}),
            self._product_payload(name=self.product_alpha.name, price='99.00'),
        )
        self.assertRedirects(response, reverse('product:list'))
        self.product_alpha.refresh_from_db()
        self.assertEqual(self.product_alpha.price, Decimal('99.00'))
        self.assertEqual(self.product_alpha.laundry, self.alpha)   # tenant intacto

    def test_duplicate_name_within_tenant_is_rejected(self):
        self.client.force_login(self.admin_alpha)
        response = self.client.post(
            reverse('product:create'),
            self._product_payload(name='carga sencilla alpha'),    # iexact
        )
        self.assertContains(response, 'Ya existe un producto con ese nombre')

    def test_cashier_without_change_perm_gets_403(self):
        self.client.force_login(self.cashier_alpha)                # solo view_*
        for url in (
            reverse('product:create'),
            reverse('product:update', kwargs={'pk': self.product_alpha.pk}),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403, url)


class CategoryCrudTests(TwoTenantTestCase):
    """Alta y edición de categorías con el mismo blindaje."""

    def test_create_assigns_session_tenant(self):
        self.client.force_login(self.admin_alpha)
        response = self.client.post(
            reverse('product:category_create'), {'name': 'Edredones'}
        )
        self.assertRedirects(response, reverse('product:list'))
        self.assertEqual(Category.objects.get(name='Edredones').laundry, self.alpha)

    def test_duplicate_category_name_within_tenant_is_rejected(self):
        self.client.force_login(self.admin_alpha)
        response = self.client.post(
            reverse('product:category_create'), {'name': 'lavado alpha'}
        )
        self.assertContains(response, 'Ya existe una categoría con ese nombre')

    def test_same_name_in_another_tenant_is_allowed(self):
        # «Planchado BRAVO» existe en Bravo; Alpha puede tener el suyo propio.
        self.client.force_login(self.admin_alpha)
        response = self.client.post(
            reverse('product:category_create'), {'name': 'Planchado BRAVO'}
        )
        self.assertRedirects(response, reverse('product:list'))
        self.assertEqual(
            Category.objects.filter(name='Planchado BRAVO').count(), 2
        )

    def test_editing_foreign_category_is_404(self):
        self.client.force_login(self.admin_alpha)
        response = self.client.get(
            reverse('product:category_update', kwargs={'pk': self.cat_bravo.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_rename_redirects_to_catalog(self):
        self.client.force_login(self.admin_alpha)
        response = self.client.post(
            reverse('product:category_update', kwargs={'pk': self.cat_alpha.pk}),
            {'name': 'Lavado y secado'},
        )
        self.assertRedirects(response, reverse('product:list'))
        self.cat_alpha.refresh_from_db()
        self.assertEqual(self.cat_alpha.name, 'Lavado y secado')

    def test_cashier_cannot_create_categories(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('product:category_create'))
        self.assertEqual(response.status_code, 403)
