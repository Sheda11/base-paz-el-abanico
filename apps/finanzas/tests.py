from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied

from apps.finanzas.models import (
    Sede, Usuario, CategoriaFinanciera, TransaccionDiaria, 
    OrdenDePago, Cliente, CuentaPorCobrar
)
from apps.auditoria.models import LogAuditoriaContable
from apps.finanzas.tasks import evaluar_cuentas_morosas_medianoche


class FinanzasAuditoriaIntegracionTests(TestCase):
    def setUp(self):
        self.sede_matriz = Sede.objects.create(
            nombre="Gran Base de Paz El Abanico",
            codigo="MAT-01",
            tipo=Sede.TipoSede.MATRIZ,
            saldo_actual=Decimal('500.00'),
            direccion="Caracas, Venezuela"
        )
        self.sede_anexa = Sede.objects.create(
            nombre="Sede Anexa Norte",
            codigo="ANX-01",
            tipo=Sede.TipoSede.ANEXA,
            saldo_actual=Decimal('100.00'),
            direccion="Sector Norte"
        )

        self.director = Usuario.objects.create_user(
            username="director_gen",
            password="Password123!",
            rol=Usuario.Rol.DIRECTOR,
            cedula_identidad="V-10000001"
        )
        self.supervisor_matriz = Usuario.objects.create_user(
            username="sup_matriz",
            password="Password123!",
            rol=Usuario.Rol.SUPERVISOR,
            sede=self.sede_matriz,
            cedula_identidad="V-10000002"
        )
        self.cajero_matriz = Usuario.objects.create_user(
            username="cajero_01",
            password="Password123!",
            rol=Usuario.Rol.CAJERO,
            sede=self.sede_matriz,
            cedula_identidad="V-10000003"
        )

        self.cat_ingreso = CategoriaFinanciera.objects.create(
            nombre="Aporte Social",
            naturaleza=CategoriaFinanciera.Naturaleza.INGRESO,
            codigo_contable="4.1.01"
        )
        self.cat_egreso = CategoriaFinanciera.objects.create(
            nombre="Mantenimiento de Instalaciones",
            naturaleza=CategoriaFinanciera.Naturaleza.EGRESO,
            codigo_contable="5.2.03"
        )

    def test_transaccion_ingreso_actualiza_saldo_y_genera_log(self):
        tx = TransaccionDiaria(
            sede=self.sede_matriz,
            categoria=self.cat_ingreso,
            tipo=TransaccionDiaria.TipoTransaccion.INGRESO,
            monto=Decimal('250.00'),
            descripcion="Inscripciones deportivas",
            numero_comprobante="DEP-001",
            registrado_por=self.cajero_matriz
        )
        tx.registrar_con_saldo(request_ip="192.168.1.100")

        self.sede_matriz.refresh_from_db()
        self.assertEqual(self.sede_matriz.saldo_actual, Decimal('750.00'))

        log = LogAuditoriaContable.objects.get(registro_id=str(tx.id))
        self.assertEqual(log.accion, LogAuditoriaContable.TipoAccion.CREAR)
        self.assertEqual(log.direccion_ip, "192.168.1.100")
        self.assertEqual(log.valores_nuevos['saldo_resultante_sede'], "750.00")

    def test_transaccion_egreso_bloquea_saldo_insuficiente(self):
        tx = TransaccionDiaria(
            sede=self.sede_matriz,
            categoria=self.cat_egreso,
            tipo=TransaccionDiaria.TipoTransaccion.EGRESO,
            monto=Decimal('1000.00'),
            descripcion="Compra de insumos mayores",
            numero_comprobante="FAC-999",
            registrado_por=self.cajero_matriz
        )
        with self.assertRaises(ValidationError):
            tx.registrar_con_saldo()

        self.sede_matriz.refresh_from_db()
        self.assertEqual(self.sede_matriz.saldo_actual, Decimal('500.00'))

    def test_inmutabilidad_de_logs_auditoria(self):
        log = LogAuditoriaContable.objects.create(
            sede=self.sede_matriz,
            usuario=self.director,
            accion=LogAuditoriaContable.TipoAccion.CREAR,
            modulo="TESORERIA",
            entidad="Test",
            registro_id="001",
            direccion_ip="127.0.0.1"
        )

        with self.assertRaises(PermissionDenied):
            log.direccion_ip = "10.0.0.1"
            log.save()

        with self.assertRaises(PermissionDenied):
            LogAuditoriaContable.objects.filter(id=log.id).update(direccion_ip="10.0.0.1")

        with self.assertRaises(PermissionDenied):
            log.delete()

        with self.assertRaises(PermissionDenied):
            LogAuditoriaContable.objects.filter(id=log.id).delete()

    def test_orden_pago_escalamiento_automatico(self):
        orden_menor = OrdenDePago.objects.create(
            sede=self.sede_matriz,
            beneficiario="Proveedor Papelería",
            concepto="Hojas de registro",
            monto=Decimal('350.00'),
            solicitado_por=self.cajero_matriz
        )
        orden_menor.iniciar_flujo()
        self.assertEqual(orden_menor.estado, OrdenDePago.Estado.PENDIENTE_SUPERVISOR)

        orden_mayor = OrdenDePago.objects.create(
            sede=self.sede_matriz,
            beneficiario="Servicios Eléctricos C.A.",
            concepto="Reparación de iluminación central",
            monto=Decimal('2500.00'),
            solicitado_por=self.cajero_matriz
        )
        orden_mayor.iniciar_flujo()
        self.assertEqual(orden_mayor.estado, OrdenDePago.Estado.PENDIENTE_DIRECTOR)

    def test_tarea_morosidad_actualiza_cuentas_vencidas(self):
        cliente = Cliente.objects.create(
            sede=self.sede_matriz,
            nombres="Carlos",
            apellidos="Pérez",
            documento="V-25111222",
            correo="carlos@example.com",
            telefono="04141234567"
        )

        hoy = timezone.now().date()
        cuenta_vencida = CuentaPorCobrar.objects.create(
            sede=self.sede_matriz,
            cliente=cliente,
            concepto="Membresía Gimnasio",
            monto_total=Decimal('50.00'),
            saldo_pendiente=Decimal('50.00'),
            fecha_vencimiento=hoy - timedelta(days=2),
            estatus=CuentaPorCobrar.Estatus.VIGENTE
        )

        cuenta_vigente = CuentaPorCobrar.objects.create(
            sede=self.sede_matriz,
            cliente=cliente,
            concepto="Taller Cultural",
            monto_total=Decimal('30.00'),
            saldo_pendiente=Decimal('30.00'),
            fecha_vencimiento=hoy + timedelta(days=7),
            estatus=CuentaPorCobrar.Estatus.VIGENTE
        )

        resultado = evaluar_cuentas_morosas_medianoche()

        cuenta_vencida.refresh_from_db()
        cuenta_vigente.refresh_from_db()

        self.assertEqual(cuenta_vencida.estatus, CuentaPorCobrar.Estatus.MOROSO)
        self.assertEqual(cuenta_vigente.estatus, CuentaPorCobrar.Estatus.VIGENTE)
        self.assertEqual(resultado['total_actualizados'], 1)
