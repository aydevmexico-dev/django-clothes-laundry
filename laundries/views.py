"""
Panel de control (dashboard) individual de cada lavandería, con filtros
analíticos combinables (periodo predefinido, rango de fechas y cliente).

Todos los agregados (KPIs, series de las gráficas, últimos tickets) nacen de
querysets que parten de `self.laundry` —resuelta por TenantRequiredMixin desde
la sesión—, por lo que es estructuralmente imposible que una métrica de otro
tenant termine en el HTML de este usuario. Los filtros solo ACOTAN dentro de
ese universo; sin filtros, el panel rinde el histórico completo del tenant.
"""
from datetime import datetime, timedelta

from django.db.models import Count, F, Min, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from django.views.generic import TemplateView

from client.models import Client
from inventory.models import Inventory
from service.models import Ticket, TicketDetail

from .mixins import TenantRequiredMixin

# Con 5 piezas o menos, el insumo aparece como "por agotarse" en el panel.
LOW_STOCK_THRESHOLD = 5

# Nombres abreviados sin depender del locale del sistema operativo.
WEEKDAYS_ES = ('Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom')
MONTHS_ES = ('Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
             'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic')

# A partir de este número de días, la serie de ventas se agrupa por mes para
# que la gráfica (y la consulta) no exploten con rangos históricos largos.
DAILY_SERIES_MAX_DAYS = 62


def _parse_iso_date(value):
    """'YYYY-MM-DD' -> date, o None si viene vacío o con basura."""
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


class DashboardView(TenantRequiredMixin, TemplateView):
    template_name = 'panel/dashboard.html'

    # ------------------------- Filtros (GET) ----------------------------
    def _parse_filters(self):
        """
        Lee y SANEA los parámetros de filtrado de la QueryString.

        * `periodo` predefinido (semana/mes) tiene prioridad y fija el rango.
        * Fechas inválidas se descartan en silencio (nunca un 500 por basura
          en la URL); si vienen invertidas, se intercambian.
        * El cliente se resuelve DENTRO del tenant: un ID de otra lavandería
          simplemente no existe y se ignora — no hay fuga ni error.

        Sin parámetros válidos, `active=False` y el panel rinde el histórico
        completo del tenant (la "consulta global" por defecto).
        """
        params = self.request.GET
        today = timezone.localdate()

        period = params.get('periodo', '')
        date_start = _parse_iso_date(params.get('fecha_inicio'))
        date_end = _parse_iso_date(params.get('fecha_fin'))

        if period == 'semana':            # desde el lunes de esta semana
            date_start = today - timedelta(days=today.weekday())
            date_end = today
        elif period == 'mes':             # desde el día 1 del mes en curso
            date_start = today.replace(day=1)
            date_end = today
        else:
            period = ''                   # valores desconocidos se descartan

        if date_start and date_end and date_start > date_end:
            date_start, date_end = date_end, date_start

        client = None
        client_param = params.get('cliente', '')
        if client_param.isdigit():
            client = (
                Client.objects.for_laundry(self.laundry)
                .filter(pk=client_param)
                .first()
            )

        return {
            'period': period,
            'date_start': date_start,
            'date_end': date_end,
            'date_start_raw': date_start.isoformat() if date_start else '',
            'date_end_raw': date_end.isoformat() if date_end else '',
            'client': client,
            'client_id': client.pk if client else None,
            'active': bool(date_start or date_end or client),
        }

    def _ticket_q(self, filters, prefix=''):
        """Q() combinable para Ticket (o TicketDetail con prefix='ticket__')."""
        q = Q()
        if filters['date_start']:
            q &= Q(**{f'{prefix}created_at__date__gte': filters['date_start']})
        if filters['date_end']:
            q &= Q(**{f'{prefix}created_at__date__lte': filters['date_end']})
        if filters['client']:
            q &= Q(**{f'{prefix}client': filters['client']})
        return q

    # --------------------- Serie de ventas adaptativa -------------------
    def _sales_series(self, tickets, start, end):
        """
        Serie de ventas entre dos fechas. Rangos cortos -> un punto por día;
        rangos largos -> un punto por mes (una sola consulta agregada en
        ambos casos; los huecos se rellenan con ceros en Python).
        """
        span_days = (end - start).days + 1
        window = tickets.filter(
            created_at__date__gte=start, created_at__date__lte=end
        )

        if span_days <= DAILY_SERIES_MAX_DAYS:
            rows = (
                window.annotate(day=TruncDate('created_at'))
                .values('day')
                .annotate(total=Sum('total'))
            )
            totals = {row['day']: float(row['total']) for row in rows}
            days = [start + timedelta(days=offset) for offset in range(span_days)]
            if span_days <= 14:
                labels = [f'{WEEKDAYS_ES[d.weekday()]} {d.day:02d}' for d in days]
            else:
                labels = [f'{d.day:02d} {MONTHS_ES[d.month - 1]}' for d in days]
            return {'labels': labels, 'values': [totals.get(d, 0.0) for d in days]}

        rows = (
            window.annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(total=Sum('total'))
        )
        totals = {}
        for row in rows:
            local = timezone.localtime(row['month'])
            totals[(local.year, local.month)] = float(row['total'])

        months, year, month = [], start.year, start.month
        while (year, month) <= (end.year, end.month):
            months.append((year, month))
            month += 1
            if month == 13:
                month, year = 1, year + 1
        return {
            'labels': [f'{MONTHS_ES[m - 1]} {y}' for y, m in months],
            'values': [totals.get((y, m), 0.0) for y, m in months],
        }

    # ----------------------------- Contexto -----------------------------
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        laundry = self.laundry                      # tenant de la SESIÓN, no de la URL
        now = timezone.now()
        today = timezone.localdate()
        week_start = today - timedelta(days=6)      # ventana móvil de 7 días
        month_start = today - timedelta(days=29)    # ventana móvil de 30 días

        filters = self._parse_filters()
        context['filters'] = filters

        # Universo del panel: SIEMPRE el tenant primero, los filtros después.
        # Sin filtros el Q() está vacío y el universo es el histórico completo.
        tickets_universe = Ticket.objects.for_laundry(laundry).filter(
            self._ticket_q(filters)
        )

        # --- KPIs de venta: del día (modo global) o del periodo filtrado ---
        sales_scope = (
            tickets_universe if filters['active']
            else tickets_universe.filter(created_at__date=today)
        )
        sales = sales_scope.aggregate(total=Sum('total'), count=Count('pk'))

        # --- KPIs financieros: UNA consulta agregada sobre el universo -----
        # (filtros condicionales Sum/Count(filter=Q): un solo SELECT)
        finance = tickets_universe.aggregate(
            settled_income=Sum('total', filter=Q(paid=True)),
            advance_income=Sum('partial_payment', filter=Q(paid=False)),
            receivable=Sum('remaining_balance', filter=Q(paid=False)),
            pending_count=Count('pk', filter=Q(paid=False)),
            deliveries_today=Count(
                'pk', filter=Q(delivery_date_time__date=today, paid=False)
            ),
            overdue_deliveries=Count(
                'pk', filter=Q(delivery_date_time__lt=now, paid=False)
            ),
        )
        collected = (finance['settled_income'] or 0) + (finance['advance_income'] or 0)
        receivable = finance['receivable'] or 0
        income_universe = collected + receivable
        collected_pct = (
            round(collected * 100 / income_universe) if income_universe else None
        )

        # --- Clientes nuevos: rango filtrado o últimos 7 días por defecto --
        client_q = Q(created_at__date__gte=filters['date_start'] or week_start)
        if filters['date_end']:
            client_q &= Q(created_at__date__lte=filters['date_end'])

        inventory = Inventory.objects.for_laundry(laundry)

        context['kpis'] = {
            'sales_today': sales['total'] or 0,
            'tickets_today': sales['count'],
            'new_clients_week': (
                Client.objects.for_laundry(laundry).filter(client_q).count()
            ),
            'clients_total': Client.objects.for_laundry(laundry).count(),
            # El inventario es estado FÍSICO actual: no se filtra por fechas.
            'inventory_items': inventory.count(),
            'low_stock': inventory.filter(quantity__lte=LOW_STOCK_THRESHOLD).count(),
            # Indicadores financieros (del universo filtrado o histórico)
            'receivable': receivable,
            'pending_count': finance['pending_count'] or 0,
            'deliveries_today': finance['deliveries_today'] or 0,
            'overdue_deliveries': finance['overdue_deliveries'] or 0,
            'collected': collected,
            'collected_pct': collected_pct,
        }

        # --- Serie de ventas: 7 días por defecto; el rango pedido al filtrar
        if filters['active']:
            series_start, series_end = filters['date_start'], filters['date_end']
            if series_start is None or series_end is None:
                # Solo cliente (o un extremo): se resuelven contra el universo.
                first = tickets_universe.aggregate(first=Min('created_at'))['first']
                fallback = timezone.localtime(first).date() if first else today
                series_start = series_start or fallback
                series_end = series_end or today
            sales_series = self._sales_series(tickets_universe, series_start, series_end)
            context['sales_series_label'] = (
                f'{series_start.strftime("%d/%m/%y")} – {series_end.strftime("%d/%m/%y")}'
            )
        else:
            sales_series = self._sales_series(tickets_universe, week_start, today)
            context['sales_series_label'] = 'últimos 7 días'

        # --- Categorías top: 30 días por defecto; el filtro manda si existe
        detail_q = Q(ticket__laundry=laundry)
        if filters['active']:
            detail_q &= self._ticket_q(filters, prefix='ticket__')
            context['categories_label'] = 'filtrado'
        else:
            detail_q &= Q(ticket__created_at__date__gte=month_start)
            context['categories_label'] = '30 días'
        top_categories = (
            TicketDetail.objects.filter(detail_q)
            .values(label=F('product__category__name'))
            .annotate(quantity=Sum('quantity'))
            .order_by('-quantity')[:6]
        )

        context['income_label'] = 'Filtrado' if filters['active'] else 'Histórico'

        # Payload único para las gráficas (|json_script en la plantilla).
        context['chart_payload'] = {
            'currency': 'MXN',
            'salesSeries': sales_series,
            'topCategories': {
                'labels': [row['label'] for row in top_categories],
                'values': [row['quantity'] for row in top_categories],
            },
            'incomeStatus': {
                'labels': ['Cobrado', 'Por cobrar'],
                'values': [float(collected), float(receivable)],
            },
        }

        # --- Últimos movimientos (del universo filtrado) -------------------
        context['latest_tickets'] = (
            tickets_universe.select_related('client').order_by('-created_at')[:8]
        )
        context['low_stock_items'] = (
            inventory.filter(quantity__lte=LOW_STOCK_THRESHOLD)
            .select_related('product')
            .order_by('quantity')[:6]
        )
        context['low_stock_threshold'] = LOW_STOCK_THRESHOLD

        # Opciones del <select> de cliente: solo id y nombre, solo el tenant.
        context['filter_clients'] = (
            Client.objects.for_laundry(laundry).only('id', 'name')
        )
        return context
