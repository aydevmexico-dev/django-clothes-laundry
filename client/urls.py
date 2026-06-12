from django.urls import path

from .views import ClientCreateView, ClientListView

app_name = 'client'

urlpatterns = [
    path('', ClientListView.as_view(), name='list'),
    path('nuevo/', ClientCreateView.as_view(), name='create'),
]
