from django.views.generic import CreateView, ListView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from django.db import transaction

from django.contrib.auth.views import LoginView, LogoutView
from .models import TransaccionDiaria, OrdenDePago, HistorialInicioSesion
from .forms import TransaccionDiariaForm, SolicitudOrdenPagoForm
from apps.auditoria.models import LogAuditoriaContable


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        usuario = self.request.user
        ip = get_client_ip(self.request)
        user_agent = self.request.META.get('HTTP_USER_AGENT', '')
        
        # Requerimiento 1: Registro inmutable de IP y timestamp en cada inicio de sesión
        HistorialInicioSesion.objects.create(
            usuario=usuario,
            direccion_ip=ip,
            user_agent=user_agent,
            exitoso=True
        )
        return response


class RegistrarTransaccionView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = TransaccionDiaria
    form_class = TransaccionDiariaForm
    template_name = 'finanzas/registrar_transaccion.html'
    success_url = reverse_lazy('finanzas:lista_transacciones')

    def test_func(self):
        permitidos = ['CAJERO', 'ANALISTA', 'SUPERVISOR', 'SUPERADMIN']
        return self.request.user.rol in permitidos

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        user = self.request.user
        ip_cliente = get_client_ip(self.request)

        transaccion = form.save(commit=False)
        transaccion.sede = user.sede
        transaccion.registrado_por = user

        try:
            transaccion.registrar_con_saldo(request_ip=ip_cliente)
            messages.success(
                self.request,
                f"Transacción {transaccion.numero_comprobante} registrada exitosamente."
            )
            return redirect(self.success_url)
        except Exception as e:
            form.add_error(None, f"Error durante la transacción bancaria: {str(e)}")
            return self.form_invalid(form)


class ListaTransaccionesView(LoginRequiredMixin, ListView):
    model = TransaccionDiaria
    template_name = 'finanzas/lista_transacciones.html'
    context_object_name = 'transacciones'
    paginate_by = 20

    def get_queryset(self):
        user = self.request.user
        if user.tiene_acceso_global:
            return TransaccionDiaria.objects.all().select_related('sede', 'categoria', 'registrado_por')
        return TransaccionDiaria.objects.filter(sede=user.sede).select_related('categoria', 'registrado_por')


class ListaOrdenesPagoView(LoginRequiredMixin, ListView):
    model = OrdenDePago
    template_name = 'finanzas/lista_ordenes_pago.html'
    context_object_name = 'ordenes'

    def get_queryset(self):
        user = self.request.user
        if user.tiene_acceso_global:
            return OrdenDePago.objects.all().select_related('sede', 'solicitado_por')
        return OrdenDePago.objects.filter(sede=user.sede).select_related('solicitado_por')


class CrearOrdenPagoView(LoginRequiredMixin, CreateView):
    model = OrdenDePago
    form_class = SolicitudOrdenPagoForm
    template_name = 'finanzas/crear_orden_pago.html'
    success_url = reverse_lazy('finanzas:lista_ordenes_pago')

    def form_valid(self, form):
        orden = form.save(commit=False)
        orden.sede = self.request.user.sede
        orden.solicitado_por = self.request.user
        orden.save()
        orden.iniciar_flujo()

        messages.info(
            self.request,
            f"Orden #{orden.id} creada en estatus: '{orden.get_estado_display()}'."
        )
        return redirect(self.success_url)


class ProcesarAprobacionOrdenView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = OrdenDePago
    fields = []
    template_name = 'finanzas/aprobar_orden_pago.html'
    success_url = reverse_lazy('finanzas:lista_ordenes_pago')

    def test_func(self):
        user = self.request.user
        orden = self.get_object()

        if orden.estado == OrdenDePago.Estado.PENDIENTE_DIRECTOR:
            return user.rol in ['DIRECTOR', 'SUPERADMIN']
        
        if orden.estado == OrdenDePago.Estado.PENDIENTE_SUPERVISOR:
            if user.rol in ['DIRECTOR', 'SUPERADMIN']:
                return True
            return user.rol == 'SUPERVISOR' and user.sede == orden.sede

        return False

    def post(self, request, *args, **kwargs):
        orden = self.get_object()
        accion = request.POST.get('accion')
        ip_cliente = get_client_ip(request)

        with transaction.atomic():
            if accion == 'APROBAR':
                orden.estado = OrdenDePago.Estado.APROBADA
                orden.fecha_aprobacion = timezone.now()
                if request.user.rol == 'DIRECTOR':
                    orden.aprobado_por_director = request.user
                else:
                    orden.aprobado_por_supervisor = request.user
                tipo_accion = LogAuditoriaContable.TipoAccion.APROBAR
                msg = f"Orden #{orden.id} aprobada con éxito."
            else:
                orden.estado = OrdenDePago.Estado.RECHAZADA
                orden.motivo_rechazo = request.POST.get('motivo_rechazo', 'Sin motivo especificado')
                tipo_accion = LogAuditoriaContable.TipoAccion.RECHAZAR
                msg = f"Orden #{orden.id} rechazada."

            orden.save()

            LogAuditoriaContable.objects.create(
                sede=orden.sede,
                usuario=request.user,
                accion=tipo_accion,
                modulo="ORDENES_PAGO",
                entidad="OrdenDePago",
                registro_id=str(orden.id),
                valores_nuevos={
                    "nuevo_estado": orden.estado,
                    "aprobador": request.user.username,
                    "rol_aprobador": request.user.rol,
                    "monto": str(orden.monto)
                },
                direccion_ip=ip_cliente
            )

        messages.success(request, msg)
        return redirect(self.success_url)
