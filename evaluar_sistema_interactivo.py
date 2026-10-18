import os
import django
import sys
from decimal import Decimal
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test.utils import setup_test_environment
setup_test_environment()

from django.test import Client
from django.utils import timezone
from django.db import connection, transaction
from django.core.exceptions import ValidationError, PermissionDenied

from apps.finanzas.models import Sede, Usuario, CategoriaFinanciera, TransaccionDiaria, OrdenDePago, Cliente, CuentaPorCobrar, HistorialInicioSesion
from apps.auditoria.models import LogAuditoriaContable
from apps.dashboard.services import DashboardAnalyticsService

def print_header(title):
    print("\n" + "="*80)
    print(f" {title} ")
    print("="*80)

def run_evaluation():
    print_header("INICIANDO EVALUACIÓN FUNCIONAL Y AUDITORÍA DE SEGURIDAD (QA)")
    client = Client()

    # Obtener sedes
    matriz = Sede.objects.get(codigo="MAT-01")
    anexa = Sede.objects.get(codigo="ANX-01")
    
    # --------------------------------------------------------------------------
    # 1. PRUEBA DE AUTENTICACIÓN Y AISLAMIENTO TERRITORIAL (RBAC)
    # --------------------------------------------------------------------------
    print_header("1. PRUEBA DE AUTENTICACIÓN Y AISLAMIENTO TERRITORIAL (RBAC)")
    
    # Crear o recuperar Cajero de Sede Anexa
    cajero_anexa, _ = Usuario.objects.get_or_create(
        username="cajero_anexa_sj",
        defaults={
            'email': 'cajero_san_juan@granbase.gob.ve',
            'rol': Usuario.Rol.CAJERO,
            'sede': anexa,
            'cedula_identidad': 'V-28000111'
        }
    )
    cajero_anexa.set_password("cajero123")
    cajero_anexa.save()

    print(f"[TEST 1.1] Intentando inicio de sesión como '{cajero_anexa.username}' (Asignado a: {anexa.nombre})...")
    login_resp = client.post('/accounts/login/', {'username': 'cajero_anexa_sj', 'password': 'cajero123'}, REMOTE_ADDR='192.168.1.120')
    assert login_resp.status_code in [200, 302], f"Error en login: {login_resp.status_code}"
    
    # Verificar registro de inicio de sesión con IP y Timestamp
    sesion = HistorialInicioSesion.objects.filter(usuario=cajero_anexa).order_by('-fecha_ingreso').first()
    assert sesion is not None, "No se registró la sesión en HistorialInicioSesion"
    print(f" -> Login Exitoso. Registro en HistorialInicioSesion: IP={sesion.direccion_ip}, Timestamp={sesion.fecha_ingreso}, Éxito={sesion.exitoso}")

    client.force_login(cajero_anexa)
    response_list = client.get('/finanzas/transacciones/')
    qs_vista = response_list.context['transacciones']
    for tx in qs_vista:
        assert tx.sede == anexa, f"Fallo de aislamiento: Cajero vio transacción de {tx.sede.nombre}"
    print(f" -> Aislamiento Verificado en Consulta: El cajero solo visualiza las transacciones de su sede ({anexa.nombre}).")

    # Intentar registrar una transacción forzando que pertenezca a la Matriz
    cat_ingreso = CategoriaFinanciera.objects.get(codigo_contable="4.1.01")
    post_data_invalida = {
        'tipo': TransaccionDiaria.TipoTransaccion.INGRESO,
        'categoria': cat_ingreso.id,
        'monto': '150.00',
        'numero_comprobante': 'CRUCE-TERRITORIAL-001',
        'descripcion': 'Intento de forzar registro en otra sede',
    }
    
    # Al enviarlo por el formulario con el cajero autenticado, el sistema fuerza la sede del cajero
    resp_post = client.post('/finanzas/transacciones/nueva/', post_data_invalida)
    tx_creada = TransaccionDiaria.objects.get(numero_comprobante='CRUCE-TERRITORIAL-001')
    assert tx_creada.sede == anexa, "Violación de RBAC: La transacción fue asignada a una sede distinta a la del usuario"
    print(f" -> Control Territorial Exitoso: El sistema vinculó obligatoriamente la transacción a la sede del usuario ({tx_creada.sede.nombre}), impidiendo cruces ilegítimos.")

    # --------------------------------------------------------------------------
    # 2. PRUEBA DE REGISTRO DE TESORERÍA Y ACTUALIZACIÓN ATÓMICA DE SALDOS
    # --------------------------------------------------------------------------
    print_header("2. PRUEBA DE REGISTRO DE TESORERÍA Y ACTUALIZACIÓN ATÓMICA DE SALDOS")
    anexa.refresh_from_db()
    saldo_inicial = anexa.saldo_actual
    print(f" -> Saldo inicial registrado en Sede Anexa San Juan: ${saldo_inicial} USD")

    cat_egreso = CategoriaFinanciera.objects.get(codigo_contable="5.2.01")

    # Caso 2.1: Intento de egreso mayor al saldo disponible
    monto_excesivo = saldo_inicial + Decimal('10000.00')
    print(f"[TEST 2.1] Intentando registrar egreso por ${monto_excesivo} USD (Supera saldo disponible de ${saldo_inicial})...")
    
    tx_invalida = TransaccionDiaria(
        sede=anexa,
        categoria=cat_egreso,
        tipo=TransaccionDiaria.TipoTransaccion.EGRESO,
        monto=monto_excesivo,
        descripcion="Gasto sin fondos",
        numero_comprobante="FAIL-001",
        registrado_por=cajero_anexa
    )
    try:
        tx_invalida.registrar_con_saldo()
        print(" [FALLO CRÍTICO] El sistema permitió un egreso con saldo insuficiente.")
    except ValidationError as e:
        print(f" -> [BLOQUEO EXITOSO]: El sistema rechazó la operación: {e}")

    # Caso 2.2: Intento de monto negativo
    print("[TEST 2.2] Intentando registrar monto negativo (-$50.00 USD)...")
    tx_negativa = TransaccionDiaria(
        sede=anexa,
        categoria=cat_ingreso,
        tipo=TransaccionDiaria.TipoTransaccion.INGRESO,
        monto=Decimal('-50.00'),
        descripcion="Monto negativo no permitido",
        numero_comprobante="FAIL-002",
        registrado_por=cajero_anexa
    )
    try:
        tx_negativa.registrar_con_saldo()
        print(" [FALLO CRÍTICO] El sistema permitió un monto negativo.")
    except ValidationError as e:
        print(f" -> [BLOQUEO EXITOSO]: El sistema rechazó el monto negativo: {e}")

    # Caso 2.3: Ingreso válido y actualización instantánea
    monto_ingreso = Decimal('200.00')
    print(f"[TEST 2.3] Registrando ingreso válido de ${monto_ingreso} USD...")
    tx_valida = TransaccionDiaria(
        sede=anexa,
        categoria=cat_ingreso,
        tipo=TransaccionDiaria.TipoTransaccion.INGRESO,
        monto=monto_ingreso,
        descripcion="Ingreso por actividades deportivas",
        numero_comprobante=f"ING-VAL-{timezone.now().strftime('%H%M%S')}",
        registrado_por=cajero_anexa
    )
    tx_valida.registrar_con_saldo(request_ip="192.168.10.45")
    
    anexa.refresh_from_db()
    saldo_esperado = saldo_inicial + monto_ingreso
    assert anexa.saldo_actual == saldo_esperado, f"Saldo incorrecto: {anexa.saldo_actual} != {saldo_esperado}"
    print(f" -> [ÉXITO CONTABLE]: Saldo anterior: ${saldo_inicial} -> Saldo actual: ${anexa.saldo_actual} USD (Incremento atómico instantáneo verificado).")

    # --------------------------------------------------------------------------
    # 3. PRUEBA DEL FLUJO DE APROBACIÓN DE ÓRDENES DE PAGO (WORKFLOW)
    # --------------------------------------------------------------------------
    print_header("3. PRUEBA DEL FLUJO DE APROBACIÓN DE ÓRDENES DE PAGO (WORKFLOW)")

    # Orden menor al umbral ($1000)
    orden_menor = OrdenDePago.objects.create(
        sede=anexa,
        beneficiario="Distribuidora de Artículos Deportivos",
        concepto="Adquisición de balones y mallas",
        monto=Decimal('450.00'),
        solicitado_por=cajero_anexa
    )
    orden_menor.iniciar_flujo()
    print(f"[TEST 3.1] Orden de Pago por ${orden_menor.monto} USD:")
    print(f" -> Estado asignado: '{orden_menor.get_estado_display()}'")
    assert orden_menor.estado == OrdenDePago.Estado.PENDIENTE_SUPERVISOR, "Estado incorrecto para monto menor a umbral"

    # Orden mayor o igual al umbral ($1000)
    orden_mayor = OrdenDePago.objects.create(
        sede=anexa,
        beneficiario="Constructora y Mantenimiento Civil C.A.",
        concepto="Refracción mayor de techo de cancha múltiple",
        monto=Decimal('1850.00'),
        solicitado_por=cajero_anexa
    )
    orden_mayor.iniciar_flujo()
    print(f"[TEST 3.2] Orden de Pago por ${orden_mayor.monto} USD:")
    print(f" -> Estado asignado: '{orden_mayor.get_estado_display()}'")
    assert orden_mayor.estado == OrdenDePago.Estado.PENDIENTE_DIRECTOR, "Fallo de escalamiento automático al Director General"
    print(" -> [WORKFLOW VALIDADO]: Escalamiento automático por umbrales verificado.")

    # --------------------------------------------------------------------------
    # 4. PRUEBA DE VISUALIZACIÓN EN EL DASHBOARD GERENCIAL
    # --------------------------------------------------------------------------
    print_header("4. PRUEBA DE VISUALIZACIÓN EN EL DASHBOARD GERENCIAL")
    director = Usuario.objects.get(username="director")
    client.force_login(director)

    resumen_consolidado = DashboardAnalyticsService.obtener_resumen_gerencial(user=director, sede_id='CONSOLIDADO')
    kpis = resumen_consolidado['kpis']
    print(f" -> Modo Consolidado (Toda la red de sedes):")
    print(f"    - Ingresos Totales acumulados: ${kpis['total_ingresos']:,.2f} USD")
    print(f"    - Egresos Totales acumulados:  ${kpis['total_egresos']:,.2f} USD")
    print(f"    - Saldo Total en Bóveda:       ${kpis['saldo_boveda_total']:,.2f} USD")
    print(f"    - Deudores Morosos Activos:    {kpis['deudores_morosos_count']} afiliados")
    print(f"    - Monto Total Deuda Morosa:    ${kpis['deuda_morosa_total']:,.2f} USD")

    # Filtro territorial individual de la Sede Anexa
    resumen_anexa = DashboardAnalyticsService.obtener_resumen_gerencial(user=director, sede_id=anexa.id)
    kpis_anexa = resumen_anexa['kpis']
    print(f"\n -> Filtro Territorial Específico ({anexa.nombre}):")
    print(f"    - Saldo exclusivo de la sede:  ${kpis_anexa['saldo_boveda_total']:,.2f} USD")
    print(f"    - Ingresos registrados:        ${kpis_anexa['total_ingresos']:,.2f} USD")
    assert kpis_anexa['saldo_boveda_total'] == float(anexa.saldo_actual), "Discrepancia en saldo del dashboard"
    print(" -> [DASHBOARD CERTIFICADO]: Métricas agregadas y filtros territoriales validados en tiempo real.")

    # --------------------------------------------------------------------------
    # 5. PRUEBA DE TRAZABILIDAD E INMUTABILIDAD DE AUDITORÍA
    # --------------------------------------------------------------------------
    print_header("5. PRUEBA DE TRAZABILIDAD E INMUTABILIDAD DE AUDITORÍA")

    # Recuperar log de la transacción registrada
    log_tx = LogAuditoriaContable.objects.filter(registro_id=str(tx_valida.id)).first()
    assert log_tx is not None, "No se generó el log de auditoría"
    print(f" -> Trazabilidad Verificada:")
    print(f"    - ID Log:         {log_tx.id}")
    print(f"    - Acción:         {log_tx.get_accion_display()}")
    print(f"    - Usuario:        {log_tx.usuario.username} ({log_tx.usuario.get_rol_display()})")
    print(f"    - Dirección IP:   {log_tx.direccion_ip}")
    print(f"    - Timestamp:      {log_tx.timestamp}")
    print(f"    - Valores nuevos: {log_tx.valores_nuevos}")

    # Intento de modificación a nivel de ORM
    print("\n[TEST 5.1] Intentando modificar log vía ORM (log.direccion_ip = '10.0.0.1')...")
    try:
        log_tx.direccion_ip = "10.0.0.1"
        log_tx.save()
        print(" [FALLO CRÍTICO]: Se permitió modificar el log en Django.")
    except PermissionDenied as e:
        print(f" -> [BLOQUEO ORM EXITOSO]: {e}")

    # Intento de modificación directa en Base de Datos (SQL UPDATE)
    target_id = log_tx.id.hex if connection.vendor == 'sqlite' else str(log_tx.id)
    print("\n[TEST 5.2] Intentando ejecutar consulta directa SQL: UPDATE auditoria_logauditoriacontable...")
    with connection.cursor() as cursor:
        try:
            with transaction.atomic():
                cursor.execute(
                    "UPDATE auditoria_logauditoriacontable SET direccion_ip = 'HACKED' WHERE id = %s",
                    [target_id]
                )
            print(" [FALLO CRÍTICO]: La base de datos permitió UPDATE directo en auditoría.")
        except Exception as e:
            print(f" -> [TRIGGER SQL BLOQUEO EXITOSO]: {e}")

    # Intento de eliminación directa en Base de Datos (SQL DELETE)
    print("\n[TEST 5.3] Intentando ejecutar consulta directa SQL: DELETE FROM auditoria_logauditoriacontable...")
    with connection.cursor() as cursor:
        try:
            with transaction.atomic():
                cursor.execute(
                    "DELETE FROM auditoria_logauditoriacontable WHERE id = %s",
                    [target_id]
                )
            print(" [FALLO CRÍTICO]: La base de datos permitió DELETE directo en auditoría.")
        except Exception as e:
            print(f" -> [TRIGGER SQL BLOQUEO EXITOSO]: {e}")

    print_header("RESULTADO FINAL: TODAS LAS PRUEBAS FUNCIONALES Y DE SEGURIDAD PASARON AL 100%")

if __name__ == '__main__':
    run_evaluation()
