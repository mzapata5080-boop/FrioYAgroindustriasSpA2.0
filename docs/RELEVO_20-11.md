# Relevo - Finanzas e Integración FIFO

## Estado actual del módulo

El módulo de Finanzas ya contempla la gestión de clientes, proveedores, facturas de compra y recepciones parciales.

Los clientes incluyen:

- RUT
- Razón social
- Teléfono
- Correo
- Dirección
- Representante
- Cargo del contacto

Los proveedores incluyen:

- RUT
- Razón social
- Giro
- Teléfono
- Correo
- Dirección
- Encargado de pagos
- Correo de pagos
- Banco
- Tipo de cuenta
- Número de cuenta

Las facturas de compra incluyen:

- Proveedor
- Fecha
- Número de documento
- Tipo de documento
- Monto
- Observaciones

Cada factura puede contener múltiples líneas de detalle mediante FacturaCompraDetalle.

Cada línea registra:

- Artículo
- Cantidad
- Precio unitario

---

# Reglas de negocio para FIFO

FIFO debe utilizar únicamente los lotes generados por recepciones efectivas de compra.

La creación de una factura NO aumenta stock.

El stock solamente aumenta cuando una recepción es confirmada.

La recepción genera:

- Movimiento de bodega tipo ingreso.
- Lote FIFO asociado.
- Actualización de stock actual.

Las salidas deben consumir siempre los lotes con fecha más antigua que aún tengan saldo disponible.

---

# Recepciones parciales

Una factura puede recibirse en varias etapas.

Ejemplo:

Factura:
100 unidades

Recepción 1:
40 unidades

Recepción 2:
30 unidades

Recepción 3:
30 unidades

La suma de las recepciones nunca puede superar la cantidad facturada.

La cantidad pendiente debe calcularse utilizando:

Cantidad facturada
menos
Cantidad recibida acumulada

---

# Descuentos

Los descuentos comerciales no deben modificar el costo FIFO histórico de los lotes.

El costo FIFO debe provenir del precio unitario registrado en la línea de factura recibida.

Los descuentos pueden registrarse posteriormente como ajuste financiero sin alterar el historial de movimientos.

---

# Impuestos

Se permite que el monto total del documento sea diferente a la suma exacta de los subtotales de las líneas.

La diferencia puede corresponder a:

- IVA
- Retenciones
- Impuestos especiales
- Gastos adicionales
- Ajustes administrativos

Por esta razón no existe una validación que obligue a que:

Suma de líneas = Monto factura

---

# Notas de crédito

Las notas de crédito no deben eliminar registros históricos.

Deben registrarse conservando la factura de referencia.

Si una nota de crédito implica devolución física de material, la devolución debe regresar al lote correspondiente o registrarse según la estrategia FIFO definida por Inventario.

---

# Integración con Inventario

FacturaCompraDetalle es la fuente oficial para:

- Artículo
- Cantidad comprada
- Precio unitario

RecepcionDetalle es la fuente oficial para:

- Cantidad efectivamente recibida
- Movimiento de ingreso asociado

Las salidas FIFO deben operar sobre los lotes derivados de recepciones y no directamente sobre las facturas.

---

# Restricciones implementadas

- No se permiten cantidades negativas.
- No se permiten cantidades iguales a cero.
- Para artículos cuya unidad es "unidad", las cantidades deben ser enteras.
- No se permite modificar artículos facturados cuando existen recepciones asociadas.
- No se permite recibir más cantidad que la pendiente.
- Los proveedores no pueden eliminarse si tienen documentos asociados.

---

# Consideraciones futuras

El cálculo FIFO debe mantenerse desacoplado del precio de venta.

El costo FIFO representa únicamente el costo de adquisición del inventario y no debe verse afectado por márgenes comerciales ni listas de precios.