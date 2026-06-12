"""Tests de seguridad del acceso: throttle anti fuerza bruta del login."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

User = get_user_model()


class LoginThrottleTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('cajero', password='correcta')

    def setUp(self):
        # La caché LocMem sobrevive entre tests del mismo proceso: se limpia
        # para que cada escenario arranque sin contadores previos.
        cache.clear()

    def _fail(self, times):
        for _ in range(times):
            self.client.post('/', {'username': 'cajero', 'password': 'mala'})

    def test_lockout_after_five_failures_even_with_correct_password(self):
        self._fail(5)
        response = self.client.post('/', {'username': 'cajero', 'password': 'correcta'})
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, 'Demasiados intentos', status_code=429)

    def test_successful_login_resets_the_counter(self):
        self._fail(4)
        response = self.client.post('/', {'username': 'cajero', 'password': 'correcta'})
        self.assertEqual(response.status_code, 302)     # entró antes del bloqueo

    def test_lockout_is_per_username_not_global(self):
        self._fail(5)
        other = User.objects.create_user('otra.caja', password='clave')
        response = self.client.post('/', {'username': 'otra.caja', 'password': 'clave'})
        self.assertEqual(response.status_code, 302)     # otro usuario no se ve afectado

    def test_locked_response_does_not_reveal_if_password_was_right(self):
        self._fail(5)
        with_wrong = self.client.post('/', {'username': 'cajero', 'password': 'mala'})
        with_right = self.client.post('/', {'username': 'cajero', 'password': 'correcta'})
        self.assertEqual(with_wrong.status_code, with_right.status_code)
