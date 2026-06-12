from django.conf import settings
from django.db import models


class TenantQuerySet(models.QuerySet):
    """QuerySet reutilizable que sabe filtrar cualquier modelo por su lavandería."""

    def for_laundry(self, laundry):
        return self.filter(laundry=laundry)


class TenantManager(models.Manager):
    """
    Manager base para todos los modelos aislados por lavandería.

    No oculta los registros por sí solo (eso sería peligroso si alguien olvida
    pasar el tenant); en su lugar expone `for_laundry()` para hacer explícito
    y obligatorio el filtrado por inquilino en cada consulta.
    """

    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db)

    def for_laundry(self, laundry):
        return self.get_queryset().for_laundry(laundry)


class Laundry(models.Model):
    """
    Tenant del sistema: cada lavandería es un inquilino independiente.

    Toda la información del POS (categorías, clientes, productos, ventas)
    cuelga de esta entidad mediante una ForeignKey, garantizando el
    aislamiento sobre una base de datos compartida.
    """

    name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name='Nombre de la lavandería',
    )
    prefix = models.CharField(
        max_length=4,
        unique=True,
        blank=True,
        verbose_name='Prefijo de folio',
        help_text='3 o 4 letras en mayúsculas. Si se deja vacío se deriva del nombre.',
    )
    folio_counter = models.PositiveBigIntegerField(
        default=0,
        editable=False,
        verbose_name='Último número de folio asignado',
        help_text='Secuencia interna de folios. Es monotónica: nunca se reutiliza.',
    )
    is_active = models.BooleanField(default=True, verbose_name='Activa')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de alta')

    class Meta:
        verbose_name = 'Lavandería'
        verbose_name_plural = 'Lavanderías'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # El prefijo se calcula una sola vez, al crear la lavandería.
        if not self.prefix:
            self.prefix = self._generate_unique_prefix()
        else:
            self.prefix = self.prefix.upper()
        super().save(*args, **kwargs)

    def _generate_unique_prefix(self):
        """Deriva un prefijo de 3 letras del nombre y lo hace único entre tenants."""
        letters = [c for c in self.name.upper() if c.isalpha()]
        base = ''.join(letters[:3]).ljust(3, 'X') or 'LAV'

        candidate = base
        suffix = 1
        others = Laundry.objects.exclude(pk=self.pk)
        while others.filter(prefix=candidate).exists():
            candidate = f'{base}{suffix}'[:4]
            suffix += 1
        return candidate


class LaundryStaff(models.Model):
    """
    Vincula un usuario de Django con la lavandería a la que pertenece.

    Es la pieza que permite el aislamiento por tenant en el admin: a partir de
    `request.user.laundry_membership` sabemos qué registros puede ver y editar.
    OneToOne con el usuario (cada persona trabaja en una sola lavandería) y
    ForeignKey hacia la lavandería (cada lavandería tiene varios empleados).
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='laundry_membership',
        verbose_name='Usuario',
    )
    laundry = models.ForeignKey(
        Laundry,
        on_delete=models.CASCADE,
        related_name='staff',
        verbose_name='Lavandería',
    )
    is_tenant_admin = models.BooleanField(
        default=False,
        verbose_name='Administrador de la lavandería',
    )

    class Meta:
        verbose_name = 'Usuario de lavandería'
        verbose_name_plural = 'Usuarios de lavandería'

    def __str__(self):
        return f'{self.user} @ {self.laundry.name}'
