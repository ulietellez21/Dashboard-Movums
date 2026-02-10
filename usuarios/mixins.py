# usuarios/mixins.py
"""
Mixins para vistas basadas en clases que usan la capa de permisos centralizada.
"""
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib import messages
from django.shortcuts import redirect

from . import permissions


class ManageRolesRequiredMixin(UserPassesTestMixin):
    """Solo quien puede gestionar roles (JEFE, Director General, Director Administrativo)."""

    def test_func(self):
        return permissions.can_manage_roles(self.request.user)

    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para acceder a la gestión de roles.")
        return redirect('dashboard')


class ManageSuppliersRequiredMixin(UserPassesTestMixin):
    """Solo quien puede gestionar proveedores (JEFE, Director General, Director Administrativo)."""

    def test_func(self):
        return permissions.can_manage_suppliers(self.request.user)

    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para gestionar proveedores.")
        return redirect('dashboard')


class FinancialReportRequiredMixin(UserPassesTestMixin):
    """Solo quien puede ver el reporte financiero (no Director Administrativo)."""

    def test_func(self):
        return permissions.can_view_financial_report(self.request.user)

    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para ver el reporte financiero.")
        return redirect('dashboard')


class KmMovumsEditRequiredMixin(UserPassesTestMixin):
    """Solo quien puede editar en Kilómetros Movums (vendedores no)."""

    def test_func(self):
        return permissions.can_edit_km_movums(self.request.user)

    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para editar en Kilómetros Movums.")
        return redirect('kilometros_dashboard')


class VentaPermissionMixin(UserPassesTestMixin):
    """Comprueba si el usuario puede ver la venta concreta (get_object)."""

    def test_func(self):
        venta = self.get_object()
        return permissions.can_view_venta(self.request.user, venta)

    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para ver esta venta.")
        return redirect('lista_ventas')
