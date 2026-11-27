"""Punto de entrada compatible con las rutas existentes; operaciones por dominio."""
from django.http import HttpResponseServerError, JsonResponse
from frio_agroindustria.api_common import CorsMiddleware
from usuarios.api import session, sign_in, sign_out
from frio_agroindustria.api_crud import collection, detail


def internal_error(request):
    message = 'Ha ocurrido un error, intente nuevamente'
    if request.path.startswith('/api/'):
        return JsonResponse({'error': message}, status=500)
    return HttpResponseServerError(message)
