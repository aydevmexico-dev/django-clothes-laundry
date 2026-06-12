"""Aislamiento del directorio de clientes y del alta desde mostrador."""
from django.urls import reverse

from laundries.tests import TwoTenantTestCase

from .models import Client


class ClientListIsolationTests(TwoTenantTestCase):

    def test_list_shows_only_own_clients(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('client:list'))
        self.assertContains(response, 'María de ALPHA')
        self.assertNotContains(response, 'Bruno de BRAVO')

    def test_search_never_escapes_the_tenant(self):
        # Buscar explícitamente el nombre del cliente rival no lo revela.
        self.client.force_login(self.cashier_alpha)
        response = self.client.get(reverse('client:list'), {'q': 'Bruno'})
        self.assertNotContains(response, 'Bruno de BRAVO')
        self.assertContains(response, 'Sin coincidencias')


class ClientCreateTests(TwoTenantTestCase):

    def test_cashier_can_create_client_in_own_tenant(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.post(reverse('client:create'), {
            'name': 'Nuevo Cliente Mostrador',
            'phone_number': '5512345678',
            'email': '',
            'rfc': '',
            'address': '',
        })
        self.assertRedirects(response, reverse('client:list'))
        created = Client.objects.get(name='Nuevo Cliente Mostrador')
        self.assertEqual(created.laundry, self.alpha)

    def test_laundry_field_in_post_is_ignored(self):
        # Intento de sembrar el cliente en el tenant rival manipulando el POST.
        self.client.force_login(self.cashier_alpha)
        self.client.post(reverse('client:create'), {
            'name': 'Cliente Inyectado',
            'laundry': self.bravo.pk,          # campo que el form NO declara
            'phone_number': '', 'email': '', 'rfc': '', 'address': '',
        })
        created = Client.objects.get(name='Cliente Inyectado')
        self.assertEqual(created.laundry, self.alpha)   # quedó en SU lavandería

    def test_duplicated_rfc_within_tenant_is_rejected(self):
        Client.objects.create(laundry=self.alpha, name='Titular', rfc='GOMA820301AB1')
        self.client.force_login(self.cashier_alpha)
        response = self.client.post(reverse('client:create'), {
            'name': 'Duplicado', 'rfc': 'GOMA820301AB1',
            'phone_number': '', 'email': '', 'address': '',
        })
        self.assertEqual(response.status_code, 200)     # se re-pinta con error
        self.assertContains(response, 'Ya existe un cliente con ese RFC')

    def test_member_without_add_permission_gets_403(self):
        self.client.force_login(self.member_no_perms)
        response = self.client.get(reverse('client:create'))
        self.assertEqual(response.status_code, 403)

    def test_malformed_phone_is_rejected(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.post(reverse('client:create'), {
            'name': 'Tel Corto', 'phone_number': '123',
            'email': '', 'rfc': '', 'address': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'exactamente 10 dígitos')
        self.assertFalse(Client.objects.filter(name='Tel Corto').exists())

    def test_malformed_rfc_is_rejected(self):
        self.client.force_login(self.cashier_alpha)
        response = self.client.post(reverse('client:create'), {
            'name': 'RFC Malo', 'rfc': 'NOVALIDO',
            'phone_number': '', 'email': '', 'address': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'formato válido')
        self.assertFalse(Client.objects.filter(name='RFC Malo').exists())

    def test_lowercase_rfc_is_normalized_to_uppercase(self):
        self.client.force_login(self.cashier_alpha)
        self.client.post(reverse('client:create'), {
            'name': 'RFC Minúsculas', 'rfc': 'goma820301ab1',
            'phone_number': '', 'email': '', 'address': '',
        })
        created = Client.objects.get(name='RFC Minúsculas')
        self.assertEqual(created.rfc, 'GOMA820301AB1')
