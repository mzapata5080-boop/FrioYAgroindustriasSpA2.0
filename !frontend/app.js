'use strict';
const $ = id => document.getElementById(id);
let csrf = '', user = null, current = '', metadata = null, loadVersion = 0;
const names = {
  trabajadores: 'Trabajadores',
  clientes: 'Clientes',
  proveedores: 'Proveedores',
  facturas: 'Facturas de compra',
  articulos: 'Inventario',
  categorias: 'Categorías',
  ingresos: 'Ingresos de bodega',
  salidas: 'Salidas de bodega',
  kardex: 'Kardex',
  obras: 'Obras y Proyectos',
  presupuestos: 'Presupuestos',
  solicitudes: 'Solicitudes de materiales'
};

function node(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}

function notice(message, bad = false) {
  const n = node('div', message, `alert alert-${bad ? 'danger' : 'success'}`);
  $('notice').replaceChildren(n);
}

async function api(path, payload) {
  const multipart = payload instanceof FormData;
  const response = await fetch(`${window.API_BASE}/${path}`, {
    method: payload === undefined ? 'GET' : 'POST',
    credentials: 'include',
    headers: payload === undefined ? {} : multipart
      ? { 'X-CSRFToken': csrf }
      : { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
    body: payload === undefined ? undefined : multipart ? payload : JSON.stringify(payload)
  });
  const body = await response.json().catch(() => ({
    error: `Respuesta inesperada (${response.status}). Comprueba el backend y la configuración CSRF.` }));
  if (!response.ok) {
    if (response.status === 401) { user = null; renderSession(); }
    throw new Error(body.error || Object.entries(body.errors || {})
      .map(([k, v]) => `${k}: ${v.join(' ')}`).join('\n') || 'No se pudo completar la operación.');
  }
  return body;
}

$('back').onclick = goHome;
$('home').onclick = event => { event.preventDefault(); if (user) goHome(); };

const hiddenColumns = new Set([
  'password', 'solicitud_id', 'solicitud_salida', 'categoria_id',
  'detalles', 'detalles_fifo', 'detalle_fifo_estado',
  'recepcion_id', 'detalle_factura_id',
  'obra_id', 'cliente_id', 'supervisor_id', 'receptor_id',
  'solicitado_por_id', 'aprobado_por_id', 'tecnicos'
]);

async function toggleActive(resource, item) {
  const nextState = !item.activo;
  const actionLabel = nextState ? 'activar' : 'desactivar';
  const label = item.codigo_parte ? `${item.codigo_parte} (${item.descripcion || ''})` : item.nombre || 'el registro';
  if (!confirm(`¿Confirmas que deseas ${actionLabel} ${label}?`)) return;
  try {
    await api(`${resource}/${item.id}/`, { activo: nextState });
    await load(resource);
    notice(`Registro ${nextState ? 'activado' : 'desactivado'} con éxito.`);
  } catch (e) {
    notice(e.message, true);
  }
}

async function handleSolicitudAction(item, accion) {
  let payload = { accion };
  if (accion === 'rechazar') {
    const motivo = prompt('Motivo de rechazo (opcional):', '');
    if (motivo === null) return;
    payload.motivo_rechazo = motivo;
  } else if (accion === 'cancelar') {
    if (!confirm('¿Cancelar esta solicitud y liberar el stock reservado pendiente?')) return;
  }
  try {
    await api(`solicitudes/${item.id}/`, payload);
    await load('solicitudes');
    const msgs = {
      aprobar: 'Solicitud aprobada y stock reservado.',
      rechazar: 'Solicitud rechazada.',
      cancelar: 'Solicitud cancelada y reserva liberada.'
    };
    notice(msgs[accion] || 'Estado actualizado.');
  } catch (e) {
    notice(e.message, true);
  }
}

async function load(resource) {
  const version = ++loadVersion;
  const response = await api(`${resource}/`);
  if (version !== loadVersion) return false;
  current = resource;
  metadata = response;
  $('editor').hidden = true;
  $('new').hidden = !metadata.can_write;
  $('dashboard').hidden = true;
  $('module-view').hidden = false;

  for (const button of $('modules').children) {
    const active = button.dataset.resource === resource;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  }

  $('section-title').textContent = names[resource] || resource;

  const container = $('records');
  container.replaceChildren();

  if (metadata.notice) {
    const banner = node('div', metadata.notice, 'alert alert-info py-2 mb-3');
    container.append(banner);
  }

  const items = metadata.items || [];
  const userRole = ((user && user.rol) || '').toLowerCase();
  const isBodegaOrGerencia = !!(user && (user.is_superuser || userRole.includes('bodega') || userRole.includes('gerencia')));

  // Configuración de columnas por recurso
  let keys = [];
  let labels = {};
  let kardexMovementLabels = {};

  if (resource === 'kardex') {
    keys = [
      'id', 'fecha_registro', 'clase_movimiento', 'articulo', 'cantidad',
      'unidad_medida', 'variacion_stock_bodega', 'costo_total_fifo',
      'obra_codigo', 'cliente_nombre', 'receptor', 'responsable', 'destino',
      'motivo_operacion', 'referencia_movimiento', 'referencia_operacion',
      'referencia_lote', 'observaciones'
    ];
    labels = {
      id: 'N° movimiento',
      fecha_registro: 'Fecha y hora',
      clase_movimiento: 'Tipo de movimiento',
      articulo: 'Artículo',
      cantidad: 'Cantidad',
      unidad_medida: 'Unidad',
      variacion_stock_bodega: 'Variación de stock',
      costo_total_fifo: 'Costo FIFO',
      obra_codigo: 'Código de obra',
      cliente_nombre: 'Cliente',
      receptor: 'Recibido por',
      responsable: 'Responsable',
      destino: 'Destino',
      motivo_operacion: 'Motivo',
      referencia_movimiento: 'Movimiento de origen',
      referencia_operacion: 'Operación anulada',
      referencia_lote: 'Lote original',
      observaciones: 'Observaciones'
    };
    kardexMovementLabels = {
      INGRESO: 'Ingreso',
      SALIDA: 'Egreso',
      AJUSTE: 'Ajuste',
      DEVOLUCION: 'Devolución',
      MERMA_BODEGA: 'Merma en bodega',
      MERMA_OBRA: 'Merma en obra',
      DEV_BODEGA: 'Devolución a bodega',
      DEV_PROVEEDOR: 'Devolución a proveedor',
      USO_INTERNO: 'Uso interno',
      CAMBIO: 'Ajuste por cambio de artículo',
      ANULAR: 'Ajuste compensatorio (anulación)'
    };
  } else if (resource === 'articulos') {
    keys = ['codigo_parte', 'descripcion', 'categoria_nombre', 'ubicacion_bodega', 'unidad_medida_display', 'stock_actual', 'stock_reservado', 'stock_minimo', 'activo'];
    labels = {
      codigo_parte: 'Código interno',
      descripcion: 'Nombre',
      categoria_nombre: 'Categoría',
      ubicacion_bodega: 'Ubicación',
      unidad_medida_display: 'Unidad',
      stock_actual: 'Stock físico',
      stock_reservado: 'Reservado',
      stock_minimo: 'Stock mínimo',
      activo: 'Estado'
    };
  } else if (resource === 'categorias') {
    keys = ['nombre', 'activo'];
    labels = { nombre: 'Nombre de la categoría', activo: 'Estado' };
  } else if (resource === 'salidas') {
    keys = ['articulo', 'cantidad', 'unidad_medida', 'numero_ot', 'cliente_nombre', 'receptor', 'responsable', 'costo_total_fifo', 'fecha_registro'];
    labels = {
      articulo: 'Artículo',
      cantidad: 'Cantidad',
      unidad_medida: 'Unidad',
      numero_ot: 'OT / Obra',
      cliente_nombre: 'Cliente',
      receptor: 'Recibido por',
      responsable: 'Despachado por',
      costo_total_fifo: 'Costo FIFO',
      fecha_registro: 'Fecha y hora'
    };
  } else if (resource === 'obras') {
    keys = ['codigo_ot', 'nombre', 'cliente_nombre', 'tipo_servicio', 'estado', 'presupuesto_estimado', 'supervisor_nombre', 'fecha_inicio'];
    labels = {
      codigo_ot: 'Código OT',
      nombre: 'Nombre de Obra',
      cliente_nombre: 'Cliente',
      tipo_servicio: 'Servicio',
      estado: 'Estado',
      presupuesto_estimado: 'Presupuesto Est.',
      supervisor_nombre: 'Supervisor',
      fecha_inicio: 'Inicio'
    };
  } else if (resource === 'presupuestos') {
    keys = ['obra_codigo', 'obra_nombre', 'version', 'estado', 'monto_materiales_estimado', 'monto_mano_obra_estimado', 'total_estimado', 'aprobado_por_nombre'];
    labels = {
      obra_codigo: 'OT',
      obra_nombre: 'Obra',
      version: 'Versión',
      estado: 'Estado',
      monto_materiales_estimado: 'Materiales',
      monto_mano_obra_estimado: 'Mano de obra',
      total_estimado: 'Total estimado',
      aprobado_por_nombre: 'Aprobado por'
    };
  } else if (resource === 'solicitudes') {
    keys = ['id', 'obra_codigo', 'articulo_nombre', 'cantidad_solicitada', 'cantidad_reservada', 'cantidad_entregada', 'unidad_medida', 'solicitado_por_nombre', 'estado'];
    labels = {
      id: 'N°',
      obra_codigo: 'OT / Obra',
      articulo_nombre: 'Artículo',
      cantidad_solicitada: 'Solicitado',
      cantidad_reservada: 'Reservado',
      cantidad_entregada: 'Entregado',
      unidad_medida: 'Unidad',
      solicitado_por_nombre: 'Solicitante',
      estado: 'Estado'
    };
  } else if (resource === 'facturas') {
    keys = ['numero_documento', 'proveedor_nombre', 'fecha', 'monto', 'detalle_count'];
    labels = {
      numero_documento: 'N° documento',
      proveedor_nombre: 'Proveedor',
      fecha: 'Fecha',
      monto: 'Monto',
      detalle_count: 'Artículos'
    };
  } else if (items.length) {
    keys = Object.keys(items[0]).filter(k => !hiddenColumns.has(k));
    labels = {
      ...Object.fromEntries((metadata.fields || []).map(f => [f.name, f.label])),
      clase_movimiento: 'Clase de movimiento',
      operacion_id: 'ID operación',
      motivo_operacion: 'Motivo',
      destino: 'Destino',
      referencia_movimiento: 'Movimiento de referencia',
      referencia_operacion: 'Operación anulada',
      referencia_lote: 'Lote original',
      variacion_stock_bodega: 'Cambio en stock de Bodega',
      responsable_id: 'ID trabajador',
      responsable: 'Trabajador',
      unidad_medida: 'Unidad',
      articulo: 'Artículo',
      fecha_registro: 'Fecha y hora'
    };
  }

  // Barra de búsqueda y filtrado
  const filterBar = node('div', undefined, 'records-filter-bar mb-3');
  const searchRow = node('div', undefined, 'd-flex flex-wrap gap-2 align-items-center justify-content-between');
  const searchGroup = node('div', undefined, 'input-group search-group flex-grow-1');
  const searchInput = node('input');
  searchInput.type = 'search';
  searchInput.id = 'table-search';
  searchInput.className = 'form-control';
  searchInput.placeholder = resource === 'articulos'
    ? 'Buscar por código interno, nombre, categoría o ubicación...'
    : resource === 'categorias'
    ? 'Buscar categoría por nombre...'
    : 'Buscar en los registros...';
  searchInput.setAttribute('aria-label', searchInput.placeholder);
  searchGroup.append(searchInput);

  let statusSelect = null;
  if (['articulos', 'categorias'].includes(resource)) {
    statusSelect = node('select');
    statusSelect.id = 'table-status-filter';
    statusSelect.className = 'form-select w-auto';
    const optAll = node('option', 'Todos los estados'); optAll.value = 'all';
    const optAct = node('option', 'Solo activos'); optAct.value = 'active';
    const optInact = node('option', 'Solo inactivos'); optInact.value = 'inactive';
    statusSelect.append(optAll, optAct, optInact);
  }

  const countBadge = node('span', `Mostrando ${items.length} de ${items.length} registro(s)`, 'text-muted small align-self-center');
  countBadge.id = 'table-count-badge';

  searchRow.append(searchGroup);
  if (statusSelect) searchRow.append(statusSelect);
  searchRow.append(countBadge);
  filterBar.append(searchRow);
  container.append(filterBar);

  if (!items.length) {
    container.append(node('p', resource === 'solicitudes' ? 'No hay solicitudes registradas.' : 'No hay registros.', 'text-muted'));
    return;
  }

  const showActionsCol = (
    (metadata.can_write && !['ingresos', 'salidas', 'kardex', 'presupuestos', 'solicitudes'].includes(resource))
    || resource === 'solicitudes'
  );

  const table = node('table', undefined, 'table table-hover align-middle text-start');
  const head = node('thead');
  const tr = node('tr');

  keys.forEach(k => tr.append(node('th', labels[k] || k.replaceAll('_', ' '))));
  if (showActionsCol) {
    tr.append(node('th', 'Acciones'));
  }
  head.append(tr);
  table.append(head);

  const tbody = node('tbody');

  items.forEach((item, index) => {
    const row = node('tr');
    row.dataset.index = String(index);

    keys.forEach(k => {
      const td = node('td');
      if (k === 'activo') {
        const badge = node('span', item.activo ? 'Activo' : 'Inactivo', `badge ${item.activo ? 'bg-success' : 'bg-secondary'}`);
        td.append(badge);
      } else if (k === 'fecha_registro') {
        td.textContent = item[k] ? new Date(item[k]).toLocaleString('es-CL') : '—';
      } else if (k === 'fecha' || k === 'fecha_inicio') {
        td.textContent = item[k] || '—';
      } else if (['monto', 'costo_total_fifo', 'presupuesto_estimado', 'monto_materiales_estimado', 'monto_mano_obra_estimado', 'total_estimado'].includes(k)) {
        td.textContent = (item[k] !== null && item[k] !== undefined)
          ? `$${Number(item[k]).toLocaleString('es-CL', { minimumFractionDigits: 0, maximumFractionDigits: 2 })} CLP`
          : '—';
      } else if (resource === 'kardex' && k === 'clase_movimiento') {
        const movementType = item[k] || item.tipo;
        td.textContent = kardexMovementLabels[movementType] || movementType || '—';
      } else if (resource === 'kardex' && k === 'variacion_stock_bodega') {
        const variation = Number(item[k]);
        td.textContent = item[k] === null || item[k] === undefined || !Number.isFinite(variation)
          ? '—'
          : `${variation > 0 ? '+' : ''}${variation}`;
      } else if (resource === 'articulos' && k === 'stock_actual') {
        const stockActual = Number(item.stock_actual || 0);
        const stockMinimo = Number(item.stock_minimo || 0);
        if (stockActual <= stockMinimo) {
          const warn = node('span', 'Bajo', 'badge bg-warning text-dark me-1');
          td.append(warn);
        }
        td.append(document.createTextNode(String(item.stock_actual ?? 0)));
      } else if (typeof item[k] === 'boolean') {
        td.textContent = item[k] ? 'Sí' : 'No';
      } else {
        td.textContent = item[k] ?? '—';
      }
      row.append(td);
    });

    if (resource === 'solicitudes') {
      const actions = node('td');
      if (isBodegaOrGerencia && item.estado === 'PENDIENTE') {
        const btnApr = node('button', 'Aprobar y Reservar', 'btn btn-sm btn-success');
        btnApr.onclick = () => handleSolicitudAction(item, 'aprobar');
        const btnRech = node('button', 'Rechazar', 'btn btn-sm btn-outline-danger ms-1');
        btnRech.onclick = () => handleSolicitudAction(item, 'rechazar');
        actions.append(btnApr, btnRech);
      }
      if (['PENDIENTE', 'APROBADA', 'PARCIAL'].includes(item.estado)) {
        const btnCanc = node('button', 'Cancelar', 'btn btn-sm btn-outline-secondary ms-1');
        btnCanc.onclick = () => handleSolicitudAction(item, 'cancelar');
        actions.append(btnCanc);
      }
      if (!actions.children.length) {
        actions.textContent = '—';
      }
      row.append(actions);
    } else if (metadata.can_write && !['ingresos', 'salidas', 'kardex', 'presupuestos'].includes(resource)) {
      const actions = node('td');
      const b = node('button', 'Editar', 'btn btn-sm btn-outline-primary');
      b.onclick = async () => {
        try {
          const d = await api(`${resource}/${item.id}/`);
          showForm(d.fields, d.item);
        } catch (e) {
          notice(e.message, true);
        }
      };
      actions.append(b);

      if (['articulos', 'categorias'].includes(resource)) {
        const toggleBtn = node(
          'button',
          item.activo ? 'Desactivar' : 'Activar',
          `btn btn-sm ${item.activo ? 'btn-outline-warning' : 'btn-outline-success'} ms-2`
        );
        toggleBtn.onclick = () => toggleActive(resource, item);
        actions.append(toggleBtn);
      }

      if (metadata.can_delete) {
        const del = node('button', 'Eliminar', 'btn btn-sm btn-outline-danger ms-2');
        del.onclick = async () => {
          if (!confirm('¿Eliminar este registro?')) return;
          try {
            await api(`${resource}/${item.id}/`, { _delete: true });
            await load(resource);
            notice('Registro eliminado.');
          } catch (e) {
            notice(e.message, true);
          }
        };
        actions.append(del);
      }

      row.append(actions);
    }

    tbody.append(row);
  });

  table.append(tbody);
  container.append(table);

  // Lógica de filtrado en vivo sin acentos ni distinción de mayúsculas
  const normalize = val => String(val || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

  function applyFilter() {
    const query = normalize(searchInput.value.trim());
    const status = statusSelect ? statusSelect.value : 'all';
    let visibleCount = 0;

    tbody.querySelectorAll('tr[data-index]').forEach(row => {
      const item = items[Number(row.dataset.index)];
      let matchesText = true;
      if (query) {
        const rowText = normalize(Object.values(item).join(' '));
        matchesText = rowText.includes(query);
      }
      let matchesStatus = true;
      if (status === 'active') matchesStatus = !!item.activo;
      else if (status === 'inactive') matchesStatus = !item.activo;

      const show = matchesText && matchesStatus;
      row.hidden = !show;
      if (show) visibleCount++;
    });

    countBadge.textContent = `Mostrando ${visibleCount} de ${items.length} registro(s)`;

    let emptyRow = tbody.querySelector('.no-matches-row');
    if (visibleCount === 0 && items.length > 0) {
      if (!emptyRow) {
        emptyRow = node('tr', undefined, 'no-matches-row');
        const td = node('td', 'No se encontraron coincidencias para la búsqueda.', 'text-center text-muted py-3');
        td.colSpan = head.querySelectorAll('th').length || 6;
        emptyRow.append(td);
        tbody.append(emptyRow);
      }
      emptyRow.hidden = false;
    } else if (emptyRow) {
      emptyRow.hidden = true;
    }
  }

  searchInput.oninput = applyFilter;
  if (statusSelect) statusSelect.onchange = applyFilter;
}

$('new').onclick = () => showForm(metadata.fields);

$('login-form').onsubmit = async event => {
  event.preventDefault();
  try {
    const d = await api('login/', { username: $('username').value, password: $('password').value });
    user = d.user;
    csrf = d.csrfToken;
    $('password').value = '';
    $('notice').replaceChildren();
    renderSession();
  } catch (e) {
    notice(e.message, true);
  }
};

$('logout').onclick = async () => {
  try {
    await api('logout/', {});
    const d = await api('session/');
    csrf = d.csrfToken;
    user = null;
    renderSession();
  } catch (e) {
    notice(e.message, true);
  }
};

(async () => {
  try {
    const d = await api('session/');
    csrf = d.csrfToken;
    user = d.user;
    renderSession();
  } catch (e) {
    notice(`No se pudo conectar: ${e.message}`, true);
  }
})();
