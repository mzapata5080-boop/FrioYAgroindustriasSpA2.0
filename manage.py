#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'frio_agroindustria.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    from django.conf import settings
    if settings.DATABASE_MODE == 'supabase' and len(sys.argv) > 1 and sys.argv[1] in ('migrate', 'flush', 'test'):
        raise SystemExit('Base Supabase existente: comando bloqueado para proteger sus datos. Para pruebas locales usa DATABASE_MODE=sqlite.')
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
