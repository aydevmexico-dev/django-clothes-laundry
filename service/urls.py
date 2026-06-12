from django.urls import path

from .views import TicketCreateView, TicketDetailView, TicketListView, TicketSettleView

app_name = 'service'

urlpatterns = [
    path('', TicketListView.as_view(), name='ticket_list'),
    path('nueva/', TicketCreateView.as_view(), name='ticket_create'),
    # La PK es local al detalle Y el queryset está acotado al tenant:
    # pedir el ticket de otra lavandería responde 404, no un recibo ajeno.
    path('<int:pk>/', TicketDetailView.as_view(), name='ticket_detail'),
    # Liquidación del saldo al entregar (solo POST, mismo aislamiento).
    path('<int:pk>/liquidar/', TicketSettleView.as_view(), name='ticket_settle'),
]
