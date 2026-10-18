import logging
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from celery import shared_task, group
from .models import CuentaPorCobrar
from apps.auditoria.models import LogAuditoriaContable

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


@shared_task(
    bind=True,
    name='apps.finanzas.tasks.evaluar_cuentas_morosas_medianoche',
    max_retries=3,
    default_retry_delay=300
)
def evaluar_cuentas_morosas_medianoche(self=None):
    hoy = timezone.now().date()
    logger.info(f"[CRON 00:00] Iniciando evaluación de cartera vencida a la fecha: {hoy}")

    cuentas_vencidas_qs = CuentaPorCobrar.objects.filter(
        estatus=CuentaPorCobrar.Estatus.VIGENTE,
        fecha_vencimiento__lt=hoy,
        saldo_pendiente__gt=Decimal('0.00')
    ).select_related('cliente', 'sede')

    total_evaluar = cuentas_vencidas_qs.count()
    if total_evaluar == 0:
        logger.info("[CRON 00:00] No se encontraron cuentas por cobrar vencidas el día de hoy.")
        return {"resultado": "Sin cambios", "total_actualizados": 0}

    logger.info(f"[CRON 00:00] Cuentas a reclasificar: {total_evaluar}")

    total_actualizados = 0
    ids_para_notificar = []
    
    lote_actual = []
    for cuenta in cuentas_vencidas_qs.iterator(chunk_size=BATCH_SIZE):
        cuenta.estatus = CuentaPorCobrar.Estatus.MOROSO
        lote_actual.append(cuenta)
        ids_para_notificar.append(str(cuenta.id))

        if len(lote_actual) >= BATCH_SIZE:
            _procesar_lote_morosidad(lote_actual)
            total_actualizados += len(lote_actual)
            lote_actual = []

    if lote_actual:
        _procesar_lote_morosidad(lote_actual)
        total_actualizados += len(lote_actual)

    LogAuditoriaContable.objects.create(
        sede=None,
        usuario=None,
        accion=LogAuditoriaContable.TipoAccion.ACTUALIZAR,
        modulo="CARTERA_COBRANZAS",
        entidad="CuentaPorCobrar",
        registro_id="BATCH_CRON_00_00",
        valores_previos={"estatus_origen": CuentaPorCobrar.Estatus.VIGENTE},
        valores_nuevos={
            "estatus_destino": CuentaPorCobrar.Estatus.MOROSO,
            "total_cuentas_afectadas": total_actualizados,
            "fecha_corte": str(hoy)
        },
        direccion_ip="127.0.0.1",
        user_agent="Celery-Beat-Worker/Engine"
    )

    if ids_para_notificar:
        try:
            grupo_notificaciones = group(
                enviar_notificacion_moroso.s(cuenta_id) for cuenta_id in ids_para_notificar
            )
            grupo_notificaciones.apply_async()
        except Exception as e:
            logger.warning(f"No se pudo encolar grupo de notificaciones: {e}")

    logger.info(f"[CRON 00:00] Finalizada con éxito. {total_actualizados} cuentas pasadas a MOROSO.")
    return {"resultado": "Éxito", "total_actualizados": total_actualizados}


def _procesar_lote_morosidad(lote):
    with transaction.atomic():
        CuentaPorCobrar.objects.bulk_update(lote, fields=['estatus'], batch_size=BATCH_SIZE)


@shared_task(
    bind=True,
    name='apps.finanzas.tasks.enviar_notificacion_moroso',
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=60,
    rate_limit='50/m'
)
def enviar_notificacion_moroso(self, cuenta_id):
    try:
        cuenta = CuentaPorCobrar.objects.select_related('cliente', 'sede').get(id=cuenta_id)
        cliente = cuenta.cliente
        logger.info(f"[NOTIFICACIÓN] Notificación emitida al cliente {cliente.documento} (Cuenta: {cuenta.id})")
        return f"Notificado: {cliente.documento}"
    except CuentaPorCobrar.DoesNotExist:
        logger.warning(f"[NOTIFICACIÓN] La cuenta {cuenta_id} ya no existe.")
        return "Cuenta no encontrada"
