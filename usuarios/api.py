"""Autenticación por sesión y emisión del token CSRF."""
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.http import require_http_methods
from frio_agroindustria.api_common import error, data, profile

@require_http_methods(['GET'])
def session(request):
    return JsonResponse({'csrfToken':get_token(request),'user':profile(request.user) if request.user.is_authenticated else None})

@require_http_methods(['POST'])
def sign_in(request):
    d = data(request)
    user = authenticate(request, username=d.get('username',''), password=d.get('password',''))
    if user is None:
        return JsonResponse({'error': 'Usuario o contraseña incorrectos'}, status=401)
    login(request,user)
    return JsonResponse({'user':profile(user),'csrfToken':get_token(request)})

@require_http_methods(['POST'])
def sign_out(request):
    logout(request)
    return JsonResponse({'ok':True})

