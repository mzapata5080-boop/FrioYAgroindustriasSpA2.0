"""Configuración de pruebas: nunca conecta a Supabase."""
import os
os.environ['DATABASE_MODE'] = 'sqlite'
from .settings import *
DATABASE_MODE = 'sqlite'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
MIGRATION_MODULES = {'inventario': None, 'obras': None}
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']