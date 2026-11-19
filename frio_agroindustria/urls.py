from django.contrib import admin
from django.urls import path
from . import api

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/session/', api.session),
    path('api/login/', api.sign_in),
    path('api/logout/', api.sign_out),
    path('api/<str:resource>/', api.collection),
    path('api/<str:resource>/<int:pk>/', api.detail),
]
