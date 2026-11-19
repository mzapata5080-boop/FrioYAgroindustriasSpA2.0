"""Punto de entrada compatible con las rutas existentes; operaciones por dominio."""
from frio_agroindustria.api_common import CorsMiddleware
from usuarios.api import session, sign_in, sign_out
from frio_agroindustria.api_crud import collection, detail
