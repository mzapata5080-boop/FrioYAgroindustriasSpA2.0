"""Registro explícito de recursos; las reglas de cada dominio se conservan."""
from usuarios.models import Trabajador
from usuarios.forms import TrabajadorCrearForm
from inventario.models import CategoriaRepuesto, Repuesto
from inventario.api_forms import CategoriaForm, ArticuloForm
from finanzas.api import FINANCE_RESOURCES

RESOURCES = {
    **FINANCE_RESOURCES,
    'trabajadores': (Trabajador, TrabajadorCrearForm, ('gerencia',)),
    'categorias': (CategoriaRepuesto, CategoriaForm, ('bodega', 'gerencia')),
    'articulos': (Repuesto, ArticuloForm, ('bodega', 'gerencia')),
}
