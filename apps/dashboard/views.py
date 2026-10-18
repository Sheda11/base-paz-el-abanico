from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View
from datetime import datetime
from apps.finanzas.models import Sede
from .services import DashboardAnalyticsService


class DashboardGerencialView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/gerencial.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        if user.tiene_acceso_global:
            context['sedes_disponibles'] = Sede.objects.filter(esta_activa=True)
            context['puede_ver_consolidado'] = True
        else:
            context['sedes_disponibles'] = [user.sede] if user.sede else []
            context['puede_ver_consolidado'] = False

        return context


class DashboardDataApiView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        sede_id = request.GET.get('sede_id')
        fecha_inicio = request.GET.get('fecha_inicio')
        fecha_fin = request.GET.get('fecha_fin')

        fmt = "%Y-%m-%d"
        f_inicio = datetime.strptime(fecha_inicio, fmt).date() if fecha_inicio else None
        f_fin = datetime.strptime(fecha_fin, fmt).date() if fecha_fin else None

        data = DashboardAnalyticsService.obtener_resumen_gerencial(
            user=request.user,
            sede_id=sede_id,
            fecha_inicio=f_inicio,
            fecha_fin=f_fin
        )
        return JsonResponse(data)
