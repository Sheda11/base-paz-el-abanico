import uuid
from decimal import Decimal
from django.db import models, transaction
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone


# ==============================================================================
# 1. ARQUITECTURA TERRITORIAL Y RBAC
# ==============================================================================

class Sede(models.Model):
    class TipoSede(models.TextChoices):
        MATRIZ = 'MATRIZ', 'Sede Central (El Abanico)'
        ANEXA = 'ANEXA', 'Sede Anexa'

    nombre = models.CharField(max_length=150, unique=True)
    codigo = models.SlugField(max_length=20, unique=True, help_text="Ej: MAT-01, ANX-01")
    tipo = models.CharField(max_length=10, choices=TipoSede.choices, default=TipoSede.ANEXA)
    direccion = models.TextField()
    telefono = models.CharField(max_length=20, blank=True)
    
    saldo_actual = models.DecimalField(
        max_digits=14, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    esta_activa = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sede"
        verbose_name_plural = "Sedes"
        ordering = ['tipo', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"


class Usuario(AbstractUser):
    class Rol(models.TextChoices):
        SUPERADMIN = 'SUPERADMIN', 'Administrador del Sistema'
        DIRECTOR = 'DIRECTOR', 'Director General'
        AUDITOR = 'AUDITOR', 'Auditor General'
        SUPERVISOR = 'SUPERVISOR', 'Supervisor de Sede'
        ANALISTA = 'ANALISTA', 'Analista Contable'
        CAJERO = 'CAJERO', 'Cajero de Sede'

    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.CAJERO)
    
    sede = models.ForeignKey(
        Sede, 
        on_delete=models.PROTECT, 
        related_name='usuarios',
        null=True, 
        blank=True,
        help_text="Requerido para roles operativos de sede"
    )

    cedula_identidad = models.CharField(max_length=20, unique=True)
    telefono = models.CharField(max_length=20, blank=True)

    def clean(self):
        super().clean()
        roles_globales = [self.Rol.SUPERADMIN, self.Rol.DIRECTOR, self.Rol.AUDITOR]
        if self.rol not in roles_globales and not self.sede:
            raise ValidationError({'sede': f'El rol {self.get_rol_display()} requiere una sede asignada.'})

    @property
    def tiene_acceso_global(self):
        return self.rol in [self.Rol.SUPERADMIN, self.Rol.DIRECTOR, self.Rol.AUDITOR]


class HistorialInicioSesion(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='inicios_sesion')
    direccion_ip = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    fecha_ingreso = models.DateTimeField(default=timezone.now)
    exitoso = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Historial de Inicio de Sesión"
        verbose_name_plural = "Historial de Inicios de Sesión"
        ordering = ['-fecha_ingreso']


# ==============================================================================
# 2. TESORERÍA, CONTABILIDAD Y CARTERA
# ==============================================================================

class CategoriaFinanciera(models.Model):
    class Naturaleza(models.TextChoices):
        INGRESO = 'INGRESO', 'Ingreso'
        EGRESO = 'EGRESO', 'Egreso'

    nombre = models.CharField(max_length=100)
    naturaleza = models.CharField(max_length=10, choices=Naturaleza.choices)
    codigo_contable = models.CharField(max_length=50, unique=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.codigo_contable} - {self.nombre} ({self.naturaleza})"


class TransaccionDiaria(models.Model):
    class TipoTransaccion(models.TextChoices):
        INGRESO = 'INGRESO', 'Ingreso Diario'
        EGRESO = 'EGRESO', 'Egreso Diario'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sede = models.ForeignKey(Sede, on_delete=models.PROTECT, related_name='transacciones')
    categoria = models.ForeignKey(CategoriaFinanciera, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=10, choices=TipoTransaccion.choices)
    
    monto = models.DecimalField(
        max_digits=14, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'), message="El monto debe ser estrictamente positivo.")]
    )
    descripcion = models.CharField(max_length=255)
    numero_comprobante = models.CharField(max_length=100, unique=True)
    comprobante_digital = models.FileField(upload_to='comprobantes/%Y/%m/', null=True, blank=True)
    
    registrado_por = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name='transacciones_registradas')
    fecha_transaccion = models.DateField(default=timezone.now)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Transacción Diaria"
        verbose_name_plural = "Transacciones Diarias"
        ordering = ['-creado_en']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(monto__gt=Decimal('0.00')),
                name='chk_transaccion_monto_positivo'
            )
        ]

    def clean(self):
        if self.categoria_id and self.categoria.naturaleza != self.tipo:
            raise ValidationError({'categoria': 'La naturaleza de la categoría no coincide con el tipo de transacción.'})
        
        if self.tipo == self.TipoTransaccion.EGRESO and self.pk is None and self.sede_id:
            if self.sede.saldo_actual < self.monto:
                raise ValidationError({'monto': f'Saldo insuficiente en {self.sede.nombre}. Saldo actual: {self.sede.saldo_actual}'})

    def registrar_con_saldo(self, request_ip=None):
        from apps.auditoria.models import LogAuditoriaContable
        self.full_clean()
        with transaction.atomic():
            sede_lock = Sede.objects.select_for_update().get(pk=self.sede_id)
            
            if self.tipo == self.TipoTransaccion.INGRESO:
                sede_lock.saldo_actual += self.monto
            else:
                if sede_lock.saldo_actual < self.monto:
                    raise ValidationError(f'Saldo insuficiente al intentar aplicar el egreso. Saldo disponible: {sede_lock.saldo_actual}')
                sede_lock.saldo_actual -= self.monto
            
            sede_lock.save()
            self.save()

            LogAuditoriaContable.objects.create(
                sede=self.sede,
                usuario=self.registrado_por,
                accion=LogAuditoriaContable.TipoAccion.CREAR,
                modulo="TESORERIA",
                entidad="TransaccionDiaria",
                registro_id=str(self.id),
                valores_nuevos={
                    "monto": str(self.monto),
                    "tipo": self.tipo,
                    "comprobante": self.numero_comprobante,
                    "saldo_resultante_sede": str(sede_lock.saldo_actual)
                },
                direccion_ip=request_ip or "0.0.0.0"
            )


class OrdenDePago(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BORRADOR', 'Borrador'
        PENDIENTE_SUPERVISOR = 'PEND_SUPERVISOR', 'Pendiente por Supervisor'
        PENDIENTE_DIRECTOR = 'PEND_DIRECTOR', 'Escalado al Director General'
        APROBADA = 'APROBADA', 'Aprobada'
        RECHAZADA = 'RECHAZADA', 'Rechazada'
        PAGADA = 'PAGADA', 'Pagada'

    UMBRAL_ESCALAMIENTO_DIRECTOR = Decimal('1000.00')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sede = models.ForeignKey(Sede, on_delete=models.PROTECT, related_name='ordenes_pago')
    beneficiario = models.CharField(max_length=200)
    concepto = models.TextField()
    monto = models.DecimalField(
        max_digits=14, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.BORRADOR)
    
    solicitado_por = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name='ordenes_solicitadas')
    aprobado_por_supervisor = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, null=True, blank=True, related_name='ordenes_aprobadas_supervisor'
    )
    aprobado_por_director = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, null=True, blank=True, related_name='ordenes_aprobadas_director'
    )
    motivo_rechazo = models.TextField(blank=True)
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)

    def iniciar_flujo(self):
        if self.monto >= self.UMBRAL_ESCALAMIENTO_DIRECTOR:
            self.estado = self.Estado.PENDIENTE_DIRECTOR
        else:
            self.estado = self.Estado.PENDIENTE_SUPERVISOR
        self.save()


class Cliente(models.Model):
    sede = models.ForeignKey(Sede, on_delete=models.PROTECT, related_name='clientes')
    nombres = models.CharField(max_length=150)
    apellidos = models.CharField(max_length=150)
    documento = models.CharField(max_length=25, unique=True)
    correo = models.EmailField()
    telefono = models.CharField(max_length=25)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.documento} - {self.nombres} {self.apellidos}"


class CuentaPorCobrar(models.Model):
    class Estatus(models.TextChoices):
        VIGENTE = 'VIGENTE', 'Vigente'
        MOROSO = 'MOROSO', 'Moroso'
        PAGADA = 'PAGADA', 'Pagada'
        ANULADA = 'ANULADA', 'Anulada'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sede = models.ForeignKey(Sede, on_delete=models.PROTECT, related_name='cuentas_por_cobrar')
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='cuentas')
    concepto = models.CharField(max_length=200)
    monto_total = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    fecha_emision = models.DateField(default=timezone.now)
    fecha_vencimiento = models.DateField()
    estatus = models.CharField(max_length=15, choices=Estatus.choices, default=Estatus.VIGENTE, db_index=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['sede', 'estatus']),
            models.Index(fields=['fecha_vencimiento', 'estatus']),
        ]
