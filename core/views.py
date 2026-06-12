from django.contrib.auth.views import LoginView
from django.core.cache import cache

# Anti fuerza bruta: tras MAX_ATTEMPTS fallos seguidos para el mismo par
# (IP, usuario), el login se bloquea LOCKOUT_SECONDS aunque la contraseña
# ya sea correcta. Un login exitoso dentro del margen reinicia el contador.
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 300


class CustomLoginView(LoginView):
    """
    Pantalla de inicio de sesión principal del POS, servida en la raíz `/`.

    Hereda de la `LoginView` nativa de Django, por lo que el manejo de CSRF, la
    validación de credenciales (`AuthenticationForm`), el arranque de la sesión
    (con rotación de ID contra fijación de sesión) y la protección contra
    redirecciones abiertas en `?next=` son los estándar y seguros del framework.
    Encima se añade un throttle de intentos fallidos por (IP, usuario).
    """

    template_name = 'login.html'
    # Si el usuario ya tiene sesión activa, no le mostramos el formulario otra
    # vez: lo mandamos directo a su destino (LOGIN_REDIRECT_URL -> /panel/).
    redirect_authenticated_user = True

    # El destino tras el login lo resuelve la propia LoginView:
    #   1º  respeta `?next=` si es una URL segura (mismo host),
    #   2º  si no, usa settings.LOGIN_REDIRECT_URL ('panel:dashboard'); el
    #       dashboard reenvía al /admin/ a los superusuarios sin lavandería.
    # Por eso NO sobreescribimos get_success_url(): el comportamiento nativo
    # ya cumple exactamente lo pedido.

    # ------------------- Throttle de fuerza bruta -----------------------
    def _throttle_key(self):
        ip = self.request.META.get('REMOTE_ADDR', 'desconocida')
        username = (self.request.POST.get('username') or '').strip().lower()
        return f'login-throttle:{ip}:{username}'

    def post(self, request, *args, **kwargs):
        if cache.get(self._throttle_key(), 0) >= MAX_LOGIN_ATTEMPTS:
            # Bloqueado: ni siquiera se validan credenciales (la respuesta es
            # idéntica con o sin contraseña correcta: no filtra información).
            context = self.get_context_data(
                form=self.get_form(),
                throttle_message=(
                    'Demasiados intentos fallidos. '
                    'Espera 5 minutos e inténtalo de nuevo.'
                ),
            )
            return self.render_to_response(context, status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        key = self._throttle_key()
        # `add` crea el contador con expiración; si ya existía, se incrementa.
        if not cache.add(key, 1, LOCKOUT_SECONDS):
            try:
                cache.incr(key)
            except ValueError:   # expiró entre el add y el incr
                cache.set(key, 1, LOCKOUT_SECONDS)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self._throttle_key())
        return super().form_valid(form)
