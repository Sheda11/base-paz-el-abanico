from django.urls import path
from .views import (
    RegistrarTransaccionView, ListaTransaccionesView,
    CrearOrdenPagoView, ListaOrdenesPagoView, ProcesarAprobacionOrdenView
)

app_name = 'finanzas'

urlpatterns = [
    path('transacciones/', ListaTransaccionesView.as_view(), name='lista_transacciones'),
    path('transacciones/nueva/', RegistrarTransaccionView.as_view(), name='registrar_transaccion'),
    path('ordenes/', ListaOrdenesPagoView.as_view(), name='lista_ordenes_pago'),
    path('ordenes/nueva/', CrearOrdenPagoView.as_view(), name='crear_orden_pago'),
    path('ordenes/<uuid:pk>/aprobar/', ProcesarAprobacionOrdenView.as_view(), name='procesar_aprobacion_orden'),
]
