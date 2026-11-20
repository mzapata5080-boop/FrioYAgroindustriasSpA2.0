# Frío y Agroindustrias SpA

Frontend independiente: `!frontend/` (HTML, Bootstrap, JavaScript).
Backend: Django con JSON, sesión, CSRF y PostgreSQL/Supabase o SQLite local.

Consulta **LEEME_PRIMERO.md** para ejecutar, probar y revisar los cambios y el estado de las migraciones.

## Punto 2: detalle del consumo FIFO

Consultar inventario/README_FIFO.md. Cada salida nueva guarda los lotes consumidos y devuelve el desglose en la API. La nueva tabla requiere la adopción SQL revisada o la migración 0005 reconciliada, no ambas. No se reconstruyen salidas históricas ni se implementan devoluciones en este paso.
