'use strict';

// Comparte autenticación, CSRF, avisos y navegación con BC2.
async function abrirOperaciones() {
 const version = ++loadVersion;
 current = 'operaciones';
 $('dashboard').hidden = true; $('module-view').hidden = false;
 $('editor').hidden = true; $('new').hidden = true;
 $('section-title').textContent = 'Mermas, devoluciones y correcciones';
 $('records').replaceChildren(node('p', 'Cargando...'));
 try {
  const datos = await api('operaciones/');
  if (version !== loadVersion || current !== 'operaciones') return;
  const zona = $('records'); zona.replaceChildren();
  const crear = node('button', 'Registrar operación', 'btn btn-danger mb-3');
  crear.type = 'button'; crear.onclick = () => formularioOperacion(datos); zona.append(crear);
  const tabla = node('table', undefined, 'table table-striped align-middle');
  const head = node('thead'), titulo = node('tr');
  ['Fecha', 'Operación', 'Artículo / cantidad', 'Obra / destino', 'Responsable', 'Motivo', 'Estado / respaldos']
   .forEach(t => titulo.append(node('th', t)));
  head.append(titulo); tabla.append(head);
  const body = node('tbody');
  datos.items.forEach(op => {
   const fila = node('tr');
   let articulo = op.articulo + ' — ' + op.cantidad + ' ' + op.unidad;
   if (op.articulo_nuevo) articulo += ' → ' + op.articulo_nuevo + ' — ' + op.cantidad_nueva;
   [new Date(op.fecha).toLocaleString('es-CL'), op.nombre, articulo,
    (op.obra || op.destino || op.proveedor || '')
      + (op.origen ? ' / salida #' + op.origen : '')
      + (op.movimiento_anulado ? ' / anula salida #' + op.movimiento_anulado : '')
      + (op.anula_a ? ' / anula operación ' + op.anula_a : '')
      + (op.documento_compra ? ' / documento ' + op.documento_compra : ''),
    '#' + op.responsable_id + ' ' + op.responsable,
    op.motivo].forEach(t => fila.append(node('td', String(t))));
   const acciones = node('td');
   acciones.append(node('p', op.anulada ? 'Anulada: el original se conserva' : 'Registrada'));
   const documentos = node('button', 'Ver / agregar respaldos', 'btn btn-sm btn-outline-secondary');
   documentos.type = 'button'; documentos.onclick = () => archivosOperacion(op);
   acciones.append(documentos); fila.append(acciones); body.append(fila);
  });
  tabla.append(body); zona.append(tabla);
  if (!datos.items.length) zona.append(node('p', 'No hay operaciones registradas.'));
 } catch (e) { if (version === loadVersion) notice(e.message, true); }
}

function formularioOperacion(datos, tipo = '') {
 const form = $('edit-form');
 if (!tipo) {
  $('editor').hidden = false;
  $('editor-title').textContent = 'Selecciona la operación';
  form.replaceChildren();
  const selector = node('select', undefined, 'form-select mb-3');
  const vacia = node('option', 'Selecciona...'); vacia.value = ''; selector.append(vacia);
  datos.tipos.forEach(opcion => {
   const option = node('option', opcion.label); option.value = opcion.id; selector.append(option);
  });
  selector.onchange = () => { if (selector.value) formularioOperacion(datos, selector.value); };
  form.append(selector);
  return;
 }
 const nombres = ['solicitud_id', 'tipo', ...datos.campos_por_tipo[tipo], 'motivo'];
 const listas = {articulo: 'articulos', articulo_nuevo: 'articulos', origen: 'salidas',
  lote: 'lotes', obra: 'obras', anula_a: 'operaciones_anulables', movimiento_anulado: 'salidas_anulables'};
 const campos = nombres.map(nombre => {
  const campo = {...datos.campos.find(c => c.name === nombre)};
  campo.required = !datos.opcionales.includes(nombre);
  if (listas[nombre]) campo.choices = [['', 'Selecciona...'],
   ...datos[listas[nombre]].map(opcion => [String(opcion.id), opcion.label])];
  return campo;
 });
 showForm(campos, {tipo, solicitud_id: requestId()});
 $('editor-title').textContent = datos.tipos.find(opcion => opcion.id === tipo).label;
 if (tipo === 'ANULAR') {
  const operacion = form.elements.namedItem('anula_a'), salida = form.elements.namedItem('movimiento_anulado');
  operacion.onchange = () => { if (operacion.value) salida.value = ''; };
  salida.onchange = () => { if (salida.value) operacion.value = ''; };
 }
 const guardar = form.querySelector('button[type="submit"]');
 form.onsubmit = async evento => {
  evento.preventDefault();
  if (guardar.disabled || !form.reportValidity()) return;
  guardar.disabled = true;
  try {
   const resultado = await api('operaciones/', Object.fromEntries(new FormData(form)));
   if (current !== 'operaciones') return;
   await abrirOperaciones();
   notice(resultado.repetida ? 'Ya estaba registrada; no se duplicó.' : 'Operación registrada.');
   if (current === 'operaciones') await archivosOperacion(resultado.item);
  } catch (error) { notice(error.message, true); }
  finally { guardar.disabled = false; }
 };
}

async function archivosOperacion(op) {
 const version = loadVersion;
 try {
  const respuesta = await api('operaciones/' + op.id + '/archivos/');
  if (version !== loadVersion || current !== 'operaciones') return;
  $('editor').hidden = false;
  $('editor-title').textContent = 'Respaldos: ' + op.nombre + ' — ' + op.id;
  const form = $('edit-form'); form.replaceChildren();
  form.append(node('p', 'La operación ya está guardada. Agregar un respaldo no vuelve a modificar stock.'));
  const lista = node('ul');
  respuesta.items.forEach(doc => {
   const li = node('li'), enlace = node('a', doc.nombre_original);
   enlace.href = window.API_BASE.replace(/\/$/, '') + '/operaciones/' + op.id + '/archivos/' + doc.id + '/';
   enlace.target = '_blank'; enlace.rel = 'noopener'; li.append(enlace); lista.append(li);
  });
  form.append(lista);
  if (!respuesta.items.length) form.append(node('p', 'Sin respaldos adjuntos.'));
  const label = node('label', 'Fotografía o PDF (máximo 10 MB)', 'form-label'); label.htmlFor = 'op-archivo';
  const input = node('input', undefined, 'form-control mb-3');
  input.type = 'file'; input.id = 'op-archivo'; input.accept = '.pdf,.png,.jpg,.jpeg'; input.required = true;
  const subir = node('button', 'Agregar respaldo', 'btn btn-primary'); subir.type = 'submit';
  const cerrar = node('button', 'Cerrar', 'btn btn-outline-secondary ms-2'); cerrar.type = 'button';
  cerrar.onclick = () => { $('editor').hidden = true; }; form.append(label, input, subir, cerrar);
  form.onsubmit = async event => {
   event.preventDefault();
   if (!form.reportValidity()) return;
   const archivo = input.files[0];
   if (archivo.size > 10 * 1024 * 1024) { notice('El máximo es 10 MB.', true); return; }
   const datos = new FormData(); datos.append('archivo', archivo);
   subir.disabled = true;
   try {
    await api('operaciones/' + op.id + '/archivos/', datos); notice('Respaldo guardado.');
    if (version === loadVersion && current === 'operaciones') await archivosOperacion(op);
   } catch (e) {
    notice('La operación sigue guardada, pero el respaldo no pudo confirmarse: ' + e.message, true);
   } finally { subir.disabled = false; }
  };
  $('editor').scrollIntoView({behavior: 'smooth', block: 'start'});
 } catch (e) {
  notice('La operación permanece guardada. No se pudieron cargar sus respaldos: ' + e.message, true);
 }
}
