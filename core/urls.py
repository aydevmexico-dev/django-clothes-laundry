"""
URL configuration for core project.

Mapa del frontend operativo (todas las rutas de negocio exigen sesión Y
membresía de lavandería; el tenant NUNCA viaja en la URL):

    /            login
    /panel/      dashboard del tenant            (namespace `panel`)
    /ventas/     historial, POS y recibo         (namespace `service`)
    /clientes/   directorio y alta de clientes   (namespace `client`)
    /productos/  catálogo de productos           (namespace `product`)
    /admin/      administración (staff global y tenant admins)
"""
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import include, path

from core.views import CustomLoginView

urlpatterns = [
    # La raíz del sitio es la pantalla de login (templates/login.html).
    path('', CustomLoginView.as_view(), name='login'),
    # Cierre de sesión -> redirige según LOGOUT_REDIRECT_URL ('login' -> '/').
    path('logout/', LogoutView.as_view(), name='logout'),

    # ----- Frontend operativo (POS), por namespaces ---------------------
    path('panel/', include('laundries.urls')),
    path('ventas/', include('service.urls')),
    path('clientes/', include('client.urls')),
    path('productos/', include('product.urls')),

    path('admin/', admin.site.urls),
]
