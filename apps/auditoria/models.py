import uuid
from django.db import models
from django.utils import timezone
from django.core.exceptions import PermissionDenied


class InmutableQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionDenied("Operación denegada: Los logs de auditoría contable no pueden ser modificados.")

    def delete(self):
        raise PermissionDenied("Operación denegada: Los logs de auditoría contable no pueden ser eliminados.")


class InmutableManager(models.Manager):
    def get_queryset(self):
        return InmutableQuerySet(self.model, using=self._db)


class LogAuditoriaContable(models.Model):
    class TipoAccion(models.TextChoices):
        CREAR = 'INSERT', 'Creación de Registro'
        ACTUALIZAR = 'UPDATE', 'Modificación'
        APROBAR = 'APPROVE', 'Aprobación de Flujo'
        RECHAZAR = 'REJECT', 'Rechazo de Flujo'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sede = models.ForeignKey('finanzas.Sede', on_delete=models.PROTECT, null=True, blank=True)
    usuario = models.ForeignKey('finanzas.Usuario', on_delete=models.PROTECT, null=True, blank=True)
    accion = models.CharField(max_length=15, choices=TipoAccion.choices)
    modulo = models.CharField(max_length=50)
    entidad = models.CharField(max_length=50)
    registro_id = models.CharField(max_length=100)
    
    valores_previos = models.JSONField(null=True, blank=True)
    valores_nuevos = models.JSONField(null=True, blank=True)
    
    direccion_ip = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True, editable=False)

    objects = InmutableManager()

    class Meta:
        verbose_name = "Log de Auditoría Contable"
        verbose_name_plural = "Logs de Auditoría Contable"
        ordering = ['-timestamp']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionDenied("Violación de Integridad: El registro de auditoría es inmutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Violación de Integridad: Los registros de auditoría no pueden ser eliminados.")
