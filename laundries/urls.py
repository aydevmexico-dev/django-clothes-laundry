"""Panel de control del tenant. SIN ID de lavandería en la URL (ver mixins)."""
from django.urls import path

from .views import DashboardView

app_name = 'panel'

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
]
