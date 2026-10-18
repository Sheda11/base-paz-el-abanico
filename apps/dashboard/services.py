from decimal import Decimal
from django.db.models import Sum, Count, Q
from django.utils import timezone
from apps.finanzas.models import TransaccionDiaria, CuentaPorCobrar, Sede


class DashboardAnalyticsService:
    @classmethod
    def obtener_resumen_gerencial(cls, user, sede_id=None, fecha_inicio=None, fecha_fin=None):
        hoy = timezone.now().date()
        if not fecha_inicio:
            fecha_inicio = hoy.replace(day=1)
        if not fecha_fin:
            fecha_fin = hoy

        if not user.tiene_acceso_global:
            sede_id = user.sede_id

        transacciones_qs = TransaccionDiaria.objects.filter(
            fecha_transaccion__range=[fecha_inicio, fecha_fin]
        )
        cuentas_morosas_qs = CuentaPorCobrar.objects.filter(
            estatus=CuentaPorCobrar.Estatus.MOROSO
        )
        sedes_qs = Sede.objects.filter(esta_activa=True)

        es_consolidado = sede_id in [None, '', 'CONSOLIDADO'] and user.tiene_acceso_global

        if not es_consolidado:
            transacciones_qs = transacciones_qs.filter(sede_id=sede_id)
            cuentas_morosas_qs = cuentas_morosas_qs.filter(sede_id=sede_id)
            sedes_qs = sedes_qs.filter(id=sede_id)

        metricas_caja = transacciones_qs.aggregate(
            total_ingresos=Sum('monto', filter=Q(tipo=TransaccionDiaria.TipoTransaccion.INGRESO)),
            total_egresos=Sum('monto', filter=Q(tipo=TransaccionDiaria.TipoTransaccion.EGRESO)),
            conteo_transacciones=Count('id')
        )

        total_ingresos = metricas_caja['total_ingresos'] or Decimal('0.00')
        total_egresos = metricas_caja['total_egresos'] or Decimal('0.00')
        balance_flujo_neto = total_ingresos - total_egresos

        metricas_morosidad = cuentas_morosas_qs.aggregate(
            cantidad_morosos=Count('cliente_id', distinct=True),
            cantidad_cuentas_vencidas=Count('id'),
            monto_total_deuda=Sum('saldo_pendiente')
        )

        saldo_boveda_total = sedes_qs.aggregate(saldo=Sum('saldo_actual'))['saldo'] or Decimal('0.00')

        desglose_sedes = []
        if es_consolidado:
            desglose_sedes = (
                Sede.objects.filter(esta_activa=True)
                .annotate(
                    ingresos_sede=Sum(
                        'transacciones__monto',
                        filter=Q(
                            transacciones__tipo=TransaccionDiaria.TipoTransaccion.INGRESO,
                            transacciones__fecha_transaccion__range=[fecha_inicio, fecha_fin]
                        )
                    ),
                    egresos_sede=Sum(
                        'transacciones__monto',
                        filter=Q(
                            transacciones__tipo=TransaccionDiaria.TipoTransaccion.EGRESO,
                            transacciones__fecha_transaccion__range=[fecha_inicio, fecha_fin]
                        )
                    ),
                    morosos_sede=Count(
                        'cuentas_por_cobrar__cliente_id',
                        filter=Q(cuentas_por_cobrar__estatus=CuentaPorCobrar.Estatus.MOROSO),
                        distinct=True
                    )
                )
                .values('id', 'nombre', 'codigo', 'tipo', 'saldo_actual', 'ingresos_sede', 'egresos_sede', 'morosos_sede')
                .order_by('-saldo_actual')
            )

        return {
            'es_consolidado': es_consolidado,
            'sede_seleccionada_id': str(sede_id) if not es_consolidado else 'CONSOLIDADO',
            'rango_fechas': {'inicio': str(fecha_inicio), 'fin': str(fecha_fin)},
            'kpis': {
                'total_ingresos': float(total_ingresos),
                'total_egresos': float(total_egresos),
                'balance_flujo_neto': float(balance_flujo_neto),
                'saldo_boveda_total': float(saldo_boveda_total),
                'deudores_morosos_count': metricas_morosidad['cantidad_morosos'] or 0,
                'cuentas_morosas_count': metricas_morosidad['cantidad_cuentas_vencidas'] or 0,
                'deuda_morosa_total': float(metricas_morosidad['monto_total_deuda'] or Decimal('0.00')),
            },
            'desglose_sedes': list(desglose_sedes)
        }
