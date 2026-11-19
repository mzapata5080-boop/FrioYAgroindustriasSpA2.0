# Fotografía del esquema, NO migración para aplicar a Supabase

El archivo 0001_current_schema.py describe solo los modelos actuales de Inventario.
Se entrega fuera de migrations para que no se ejecute automáticamente.
No sustituye inventario.0001_initial que ya figura aplicada en Supabase.
Las columnas históricas adicionales de la base (por ejemplo cliente_planta_id y tecnico_id) no pueden reconstruirse íntegramente con el código recibido.

Pasos para reconciliar con el equipo:
1. Recuperar el archivo original 0001_initial y los modelos de ese momento.
2. Comparar su estado con la estructura actual mediante auditar_inventario y las definiciones SQL originales.
3. Documentar los ALTER de numeric(15,2) y CREATE de recepciones_ingreso ya aplicados.
4. Preparar una migración posterior que represente esos cambios, con operaciones de estado y de base diferenciadas si corresponde.
5. Probar la cadena completa y su adopción sobre una copia de la base antes de autorizarla en la compartida.

No usar --fake o --fake-initial para ocultar discrepancias de estructura sin verificarlas.
