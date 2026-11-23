from django.db import models
from django.db.models import Q
from django.contrib.auth.models import AbstractUser

class Trabajador(AbstractUser):
    rut = models.CharField(max_length=12, blank=True, null=True)
    telefono = models.CharField(max_length=15, blank=True, null=True)

    @property
    def rol(self):
        if self.groups.filter(Q(name__iexact='Gerencia') | Q(name__iexact='Gerente')).exists():
            return 'gerencia'
        if self.groups.exists():
            return self.groups.first().name.lower()
        return ''

    def __str__(self):
        return f"{self.username} - {self.get_full_name()}"