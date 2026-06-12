"""Catálogo de productos del tenant: consulta, alta y edición."""
from django.conf import settings
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from laundries.mixins import TenantPermissionRequiredMixin, TenantQuerysetMixin

from .forms import CategoryForm, ProductForm
from .models import Category, Product


class ProductListView(TenantPermissionRequiredMixin, TenantQuerysetMixin, ListView):
    """
    Catálogo con búsqueda y filtro por categoría.

    El queryset SIEMPRE parte del filtro por `self.laundry` (TenantQuerysetMixin);
    la búsqueda y la categoría solo acotan dentro de ese universo.
    """

    model = Product
    permission_required = 'product.view_product'
    template_name = 'product/product_list.html'
    context_object_name = 'products'
    paginate_by = settings.ITEMS_PER_PAGE

    def get_queryset(self):
        qs = (
            super().get_queryset()
            .select_related('category', 'inventory')
            .order_by('category__name', 'name')
        )
        query = self.request.GET.get('q', '').strip()
        if query:
            qs = qs.filter(name__icontains=query)
        category_id = self.request.GET.get('categoria', '')
        if category_id.isdigit():
            qs = qs.filter(category_id=category_id)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        categories = Category.objects.for_laundry(self.laundry)
        context['categories'] = categories
        context['query'] = self.request.GET.get('q', '').strip()
        category_id = self.request.GET.get('categoria', '')
        context['active_category'] = category_id
        # La categoría activa como objeto (para el botón "Editar categoría").
        context['active_category_obj'] = (
            categories.filter(pk=category_id).first() if category_id.isdigit() else None
        )
        return context


# ---------------------------------------------------------------------------
# Bases compartidas del CRUD: el tenant se asigna/filtra SIEMPRE en el backend
# ---------------------------------------------------------------------------
class CatalogFormMixin:
    """
    Comportamiento común de las cuatro pantallas de alta/edición del catálogo:

      * El formulario recibe el tenant para acotar sus <select> y validar
        unicidad por lavandería.
      * En el alta, `form_valid()` asigna la lavandería de la SESIÓN al objeto
        nuevo: el usuario jamás elige tenant (ni existe el campo para ello).
      * Tras guardar, SIEMPRE se vuelve al listado del catálogo: ninguna
        pestaña queda rota tras un POST.
    """

    success_url = reverse_lazy('product:list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['laundry'] = self.laundry
        return kwargs

    def form_valid(self, form):
        # En edición la lavandería ya viene puesta y NO se toca; en alta se
        # asigna aquí, desde la sesión: a prueba de manipulación del POST.
        if not form.instance.pk:
            form.instance.laundry = self.laundry
        response = super().form_valid(form)
        messages.success(self.request, self.success_message.format(obj=self.object))
        return response


class CategoryCreateView(CatalogFormMixin, TenantPermissionRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    permission_required = 'product.add_category'
    template_name = 'product/category_form.html'
    success_message = 'Categoría «{obj}» creada.'


class CategoryUpdateView(
    CatalogFormMixin, TenantPermissionRequiredMixin, TenantQuerysetMixin, UpdateView
):
    """
    Edición de categoría. `TenantQuerysetMixin` acota el queryset que usa
    `get_object()`: pedir la PK de otra lavandería responde 404 — para este
    usuario, ese registro no existe.
    """

    model = Category
    form_class = CategoryForm
    permission_required = 'product.change_category'
    template_name = 'product/category_form.html'
    success_message = 'Categoría «{obj}» actualizada.'


class ProductCreateView(CatalogFormMixin, TenantPermissionRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    permission_required = 'product.add_product'
    template_name = 'product/product_form.html'
    success_message = 'Producto «{obj}» creado.'


class ProductUpdateView(
    CatalogFormMixin, TenantPermissionRequiredMixin, TenantQuerysetMixin, UpdateView
):
    """Edición de producto, con el mismo 404 para PKs de otro tenant."""

    model = Product
    form_class = ProductForm
    permission_required = 'product.change_product'
    template_name = 'product/product_form.html'
    success_message = 'Producto «{obj}» actualizado.'
