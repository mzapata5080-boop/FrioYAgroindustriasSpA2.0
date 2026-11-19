# Frío y Agroindustrias SpA

Frontend independiente: `!frontend/` (HTML, Bootstrap, JavaScript).
Backend: Django con JSON, sesión, CSRF y PostgreSQL/Supabase o SQLite local.

Consulta **LEEME_PRIMERO.md** para ejecutar, probar y revisar los cambios y el estado de las migraciones.

## FIFO de existencias

Consultar **FIFO.md**: consumo de lotes antiguos, cálculo por precio original y auditoría. No utiliza descuentos porcentuales. La adopción del esquema y el historial Django deben revisarse según el entorno; no ejecutar migraciones improvisadas en Supabase.
