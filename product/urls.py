from django.urls import path

from .views import (
    CategoryCreateView,
    CategoryUpdateView,
    ProductCreateView,
    ProductListView,
    ProductUpdateView,
)

app_name = 'product'

urlpatterns = [
    path('', ProductListView.as_view(), name='list'),
    path('nuevo/', ProductCreateView.as_view(), name='create'),
    # PK local + queryset acotado al tenant: editar un ID ajeno es 404.
    path('<int:pk>/editar/', ProductUpdateView.as_view(), name='update'),
    path('categorias/nueva/', CategoryCreateView.as_view(), name='category_create'),
    path('categorias/<int:pk>/editar/', CategoryUpdateView.as_view(), name='category_update'),
]
