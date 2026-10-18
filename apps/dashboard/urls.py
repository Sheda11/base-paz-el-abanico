from django.urls import path
from .views import DashboardGerencialView, DashboardDataApiView

app_name = 'dashboard'

urlpatterns = [
    path('', DashboardGerencialView.as_view(), name='gerencial'),
    path('api/data/', DashboardDataApiView.as_view(), name='api_data'),
]
