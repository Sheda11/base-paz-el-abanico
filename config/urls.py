from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LogoutView
from apps.finanzas.views import CustomLoginView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', CustomLoginView.as_view(), name='login'),
    path('login/', CustomLoginView.as_view(), name='login_direct'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('finanzas/', include('apps.finanzas.urls')),
    path('', include('apps.dashboard.urls')),
]
