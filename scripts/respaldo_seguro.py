"""Genera un respaldo lógico en backups/ sin modificar la base de datos."""
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'frio_agroindustria.settings')

import django
django.setup()

from django.conf import settings
from django.core.management import call_command

backups_dir = ROOT / 'backups'
backups_dir.mkdir(exist_ok=True)
stamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
out_file = backups_dir / f'respaldo_{settings.DATABASE_MODE}_{stamp}.json'

with out_file.open('w', encoding='utf-8') as fh:
    call_command(
        'dumpdata',
        natural_foreign=True,
        natural_primary=True,
        exclude=['contenttypes', 'auth.Permission', 'sessions.Session'],
        indent=2,
        stdout=fh,
    )

print(f'Respaldo creado en: {out_file}')