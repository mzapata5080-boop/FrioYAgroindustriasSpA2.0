"""Recursos comerciales y sus permisos; validación en los formularios existentes."""
from .models import Cliente, Proveedor, FacturaCompra
from .forms import ClienteForm, ProveedorForm, FacturaCompraForm

FINANCE_RESOURCES = {
    'clientes': (Cliente, ClienteForm, ('finanzas', 'gerencia')),
    'proveedores': (Proveedor, ProveedorForm, ('finanzas', 'gerencia')),
    'facturas': (FacturaCompra, FacturaCompraForm, ('finanzas', 'gerencia')),
}
