from functools import wraps
from django.core.exceptions import PermissionDenied

def solo_finanzas(view_func):

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.rol != "finanzas":
            raise PermissionDenied("No posee permisos para acceder")
        return view_func(
            request,
            *args,
            **kwargs
        )
    return wrapper