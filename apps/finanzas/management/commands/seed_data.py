from decimal import Decimal
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.finanzas.models import Sede, Usuario, CategoriaFinanciera, TransaccionDiaria, Cliente, CuentaPorCobrar


class Command(BaseCommand):
    help = 'Carga datos iniciales de demostración para la Gran Base de Paz El Abanico'

    def handle(self, *args, **options):
        self.stdout.write("Inicializando datos maestros...")

        # 1. Sedes
        matriz, _ = Sede.objects.get_or_create(
            codigo="MAT-01",
            defaults={
                'nombre': 'Gran Base de Paz "El Abanico" (Matriz)',
                'tipo': Sede.TipoSede.MATRIZ,
                'saldo_actual': Decimal('15420.50'),
                'direccion': 'Av. Principal El Abanico, Caracas',
                'telefono': '0212-5551234'
            }
        )
        anexa_1, _ = Sede.objects.get_or_create(
            codigo="ANX-01",
            defaults={
                'nombre': 'Sede Anexa San Juan',
                'tipo': Sede.TipoSede.ANEXA,
                'saldo_actual': Decimal('4250.00'),
                'direccion': 'Parroquia San Juan',
                'telefono': '0212-5555678'
            }
        )
        anexa_2, _ = Sede.objects.get_or_create(
            codigo="ANX-02",
            defaults={
                'nombre': 'Sede Anexa El Recreo',
                'tipo': Sede.TipoSede.ANEXA,
                'saldo_actual': Decimal('3180.75'),
                'direccion': 'Sector El Recreo',
                'telefono': '0212-5559012'
            }
        )

        # 2. Categorías
        cat_inscripcion, _ = CategoriaFinanciera.objects.get_or_create(
            codigo_contable="4.1.01",
            defaults={'nombre': 'Inscripciones y Membresías', 'naturaleza': CategoriaFinanciera.Naturaleza.INGRESO}
        )
        cat_aporte, _ = CategoriaFinanciera.objects.get_or_create(
            codigo_contable="4.1.02",
            defaults={'nombre': 'Aporte Comunitario / Donaciones', 'naturaleza': CategoriaFinanciera.Naturaleza.INGRESO}
        )
        cat_mantenimiento, _ = CategoriaFinanciera.objects.get_or_create(
            codigo_contable="5.2.01",
            defaults={'nombre': 'Mantenimiento de Canchas e Infraestructura', 'naturaleza': CategoriaFinanciera.Naturaleza.EGRESO}
        )

        # 3. Usuarios
        if not Usuario.objects.filter(username='director').exists():
            Usuario.objects.create_superuser(
                username='director',
                email='director@granbasedepaz.gob.ve',
                password='admin',
                rol=Usuario.Rol.DIRECTOR,
                cedula_identidad='V-12345678'
            )
            self.stdout.write(self.style.SUCCESS("Usuario Director creado: director / admin"))

        if not Usuario.objects.filter(username='cajero_matriz').exists():
            Usuario.objects.create_user(
                username='cajero_matriz',
                password='password',
                rol=Usuario.Rol.CAJERO,
                sede=matriz,
                cedula_identidad='V-20111222'
            )
            self.stdout.write(self.style.SUCCESS("Usuario Cajero creado: cajero_matriz / password"))

        # 4. Clientes y Cuentas por Cobrar (Deudores Morosos de prueba)
        cliente_moroso, _ = Cliente.objects.get_or_create(
            documento="V-18999888",
            defaults={
                'sede': matriz,
                'nombres': 'José',
                'apellidos': 'Rodríguez',
                'correo': 'jose.rodriguez@example.com',
                'telefono': '0412-1112233'
            }
        )

        hoy = timezone.now().date()
        CuentaPorCobrar.objects.get_or_create(
            cliente=cliente_moroso,
            concepto="Mensualidad Academia de Boxeo",
            defaults={
                'sede': matriz,
                'monto_total': Decimal('45.00'),
                'saldo_pendiente': Decimal('45.00'),
                'fecha_emision': hoy - timedelta(days=40),
                'fecha_vencimiento': hoy - timedelta(days=10),
                'estatus': CuentaPorCobrar.Estatus.MOROSO
            }
        )

        self.stdout.write(self.style.SUCCESS("¡Datos iniciales de demostración cargados exitosamente!"))
