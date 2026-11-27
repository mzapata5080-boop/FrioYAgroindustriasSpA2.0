'use strict';
const $ = id => document.getElementById(id);
let csrf = '', user = null, current = '', metadata = null, loadVersion = 0;
const activeFilters = Object.create(null);
const activeSearch = Object.create(null);
const names = {
  trabajadores: 'Trabajadores',
  clientes: 'Clientes',
  proveedores: 'Proveedores',
  facturas: 'Facturas de compra',
  precios: 'Precios e historial',
  'presupuestos-venta': 'Presupuestos de venta',
  'detalles-presupuesto': 'Artículos de presupuestos',
  'documentos-venta': 'Documentos de venta',
  'notas-credito': 'Notas de crédito',
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

function formatFinanceAmount(value) {
  const amount = Number(value || 0);
  return `$${(Number.isFinite(amount) ? amount : 0).toLocaleString('es-CL', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2
  })} CLP`;
}

function sumFinanceAmount(items, field) {
  return items.reduce((sum, item) => {
    const value = Number(item[field] || 0);
    return sum + (Number.isFinite(value) ? value : 0);
  }, 0);
}

function renderFinanceSummary(resource, items, container) {
  let metrics = [];
  if (resource === 'presupuestos-venta') {
    metrics = [
      { label: 'Total cotizado', value: formatFinanceAmount(sumFinanceAmount(items, 'total')) },
      { label: 'Pendientes de aprobación', value: items.filter(item => item.estado === 'BORRADOR').length },
      { label: 'Aprobados', value: items.filter(item => item.estado === 'APROBADO').length },
      { label: 'Rechazados', value: items.filter(item => item.estado === 'RECHAZADO').length }
    ];
  } else if (resource === 'detalles-presupuesto') {
    metrics = [
      { label: 'Artículos cotizados', value: items.length },
      { label: 'Unidades cotizadas', value: items.reduce((sum, item) => sum + Number(item.cantidad || 0), 0) },
      { label: 'Total en líneas', value: formatFinanceAmount(sumFinanceAmount(items, 'subtotal')) }
    ];
  } else if (resource === 'documentos-venta') {
    const vigentes = items.filter(item => !item.anulado);
    metrics = [
      { label: 'Total vigente', value: formatFinanceAmount(sumFinanceAmount(vigentes, 'total')) },
      { label: 'Saldo pendiente', value: formatFinanceAmount(sumFinanceAmount(vigentes, 'saldo')) },
      {
        label: 'Pagos parciales',
        value: vigentes.filter(item =>
          Number(item.pagos_count || 0) > 0 && Number(item.saldo || 0) > 0
        ).length
      },
      {
        label: 'Saldados',
        value: vigentes.filter(item => Number(item.saldo || 0) <= 0).length
      }
    ];
  } else if (resource === 'notas-credito') {
    metrics = [
      { label: 'Notas registradas', value: items.length },
      { label: 'Total acreditado', value: formatFinanceAmount(sumFinanceAmount(items, 'monto')) }
    ];
  }
  if (!metrics.length) return;

  const grid = node('section', undefined, 'finance-summary-grid');
  grid.setAttribute('aria-label', 'Resumen financiero');
  metrics.forEach(metric => {
    const card = node('article', undefined, 'card finance-summary-card');
    card.append(
      node('span', metric.label, 'finance-summary-label'),
      node('strong', String(metric.value), 'finance-summary-value')
    );
    grid.append(card);
  });
  container.append(grid);
}

function financeStatusBadge(status) {
  const styles = {
    BORRADOR: ['Borrador', 'bg-warning text-dark'],
    APROBADO: ['Aprobado', 'bg-success'],
    RECHAZADO: ['Rechazado', 'bg-danger']
  };
  const [label, style] = styles[status] || [status || 'Sin estado', 'bg-secondary'];
  return node('span', label, `badge finance-status ${style}`);
}

const activeToasts = new Set();
let loadingRequests = 0;
const buttonDisabledStates = new Map();

function notify(message, type = 'success') {
  const styles = {
    success: ['bi-check-circle-fill', 'Éxito'],
    warning: ['bi-exclamation-triangle-fill', 'Atención'],
    error: ['bi-x-circle-fill', 'Error'],
    info: ['bi-info-circle-fill', 'Información']
  };
  const [iconName, label] = styles[type] || styles.info;
  const toast = node('div', undefined, `app-toast toast-${type}`);
  toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
  const icon = node('i', undefined, `bi ${iconName} toast-icon`);
  icon.setAttribute('aria-hidden', 'true');
  const content = node('span', message, 'toast-message');
  const close = node('button', undefined, 'btn-close toast-close');
  close.type = 'button';
  close.setAttribute('aria-label', `Cerrar notificación: ${label}`);
  close.onclick = () => dismissToast(toast);
  toast.append(icon, content, close);
  $('toast-container').append(toast);
  activeToasts.add(toast);
  window.requestAnimationFrame(() => toast.classList.add('toast-visible'));
  window.setTimeout(() => dismissToast(toast), 5000);
}

function dismissToast(toast) {
  if (!activeToasts.has(toast)) return;
  toast.classList.remove('toast-visible');
  window.setTimeout(() => {
    toast.remove();
    activeToasts.delete(toast);
  }, 220);
}

function notice(message, bad = false) {
  notify(message, bad ? 'error' : 'success');
}

function beginGlobalLoading() {
  loadingRequests++;
  if (loadingRequests !== 1) return;
  const overlay = $('global-loading');
  overlay.hidden = false;
  overlay.setAttribute('aria-hidden', 'false');
  document.body.classList.add('is-loading');
  document.querySelectorAll('button').forEach(button => {
    buttonDisabledStates.set(button, button.disabled);
    button.disabled = true;
  });
}

function endGlobalLoading() {
  loadingRequests = Math.max(0, loadingRequests - 1);
  if (loadingRequests !== 0) return;
  const overlay = $('global-loading');
  overlay.hidden = true;
  overlay.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('is-loading');
  buttonDisabledStates.forEach((disabled, button) => {
    if (button.isConnected) button.disabled = disabled;
  });
  buttonDisabledStates.clear();
}

async function api(path, payload) {
  const showLoader = !path.startsWith('calculo-comercial/');
  if (showLoader) beginGlobalLoading();
  try {
    const multipart = payload instanceof FormData;
    const endpoint = `${window.API_BASE}/${path}`;
    const resource = String(path).split('?')[0].split('/').filter(Boolean)[0] || 'desconocido';
    let response;
    try {
      response = await fetch(endpoint, {
        method: payload === undefined ? 'GET' : 'POST',
        credentials: 'include',
        headers: payload === undefined ? {} : multipart
          ? { 'X-CSRFToken': csrf }
          : { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: payload === undefined ? undefined : multipart ? payload : JSON.stringify(payload)
      });
    } catch (error) {
      logFrontendRequestFailure(resource, endpoint, null);
      throw error;
    }
    if (!response.ok) logFrontendRequestFailure(resource, endpoint, response.status);
    const body = await response.json().catch(() => ({
      error: response.status >= 500
        ? 'Ha ocurrido un error, intente nuevamente'
        : response.status === 403
        ? 'No posee permisos para acceder'
        : response.status === 401
        ? 'Su sesión ha expirado'
        : `Respuesta inesperada (${response.status}). Comprueba el backend y la configuración CSRF.`
    }));
    if (!response.ok) {
      if (response.status === 401) { user = null; renderSession(); }
      const message = response.status >= 500
        ? 'Ha ocurrido un error, intente nuevamente'
        : body.error || Object.entries(body.errors || {})
        .map(([k, v]) => `${k}: ${v.join(' ')}`).join('\n') || 'No se pudo completar la operación.';
      throw new Error(message);
    }
    return body;
  } finally {
    if (showLoader) endGlobalLoading();
  }
}

$('back').onclick = goHome;
$('home').onclick = event => { event.preventDefault(); if (user) goHome(); };

const hiddenColumns = new Set(['totales', 'calculo_activo', 'calcular_totales', 'confirmada',
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

async function handlePresupuestoDecision(item, accion) {
  let motivo = '';
  if (accion === 'rechazar') {
    motivo = prompt('Motivo de rechazo:', '');
    if (motivo === null) return;
  } else if (!confirm(`¿Aprobar el presupuesto ${item.numero}?`)) {
    return;
  }
  try {
    await api(`presupuestos-venta/${item.id}/decision/`, { accion, motivo });
    await load('presupuestos-venta');
    notice(accion === 'aprobar'
      ? `El presupuesto ${item.numero} fue aprobado correctamente.`
      : `El presupuesto ${item.numero} fue rechazado.`);
  } catch (e) {
    notice(e.message, true);
  }
}

async function handleDocumentoAnular(item) {
  const motivo = prompt('Motivo de anulación:', '');
  if (motivo === null) return;
  try {
    await api(`documentos-venta/${item.id}/anular/`, { motivo });
    await load('documentos-venta');
    notice('Documento anulado.');
  } catch (e) {
    notice(e.message, true);
  }
}

async function openDocumentoPagos(documento) {
  try {
    const data = await api(`documentos-venta/${documento.id}/pagos/`);
    $('editor').hidden = false;
    $('editor-title').textContent = `Pagos: ${documento.numero_documento}`;
    const form = $('edit-form');
    form.replaceChildren();

    const heading = node(
      'p',
      `Total: $${Number(data.total).toLocaleString('es-CL')} CLP · Saldo: $${Number(data.saldo).toLocaleString('es-CL')} CLP`,
      'text-muted'
    );
    form.append(heading);
    const table = node('table', undefined, 'table table-sm table-striped');
    const head = node('thead'), headerRow = node('tr');
    ['Fecha', 'Monto', 'Método', 'Referencia', 'Registrado por'].forEach(
      title => headerRow.append(node('th', title))
    );
    head.append(headerRow);
    table.append(head);
    const body = node('tbody');
    data.items.forEach(payment => {
      const row = node('tr');
      [
        payment.fecha_pago,
        `$${Number(payment.monto).toLocaleString('es-CL')} CLP`,
        payment.metodo,
        payment.referencia || '—',
        payment.registrado_por_nombre
      ].forEach(value => row.append(node('td', String(value ?? '—'))));
      body.append(row);
    });
    table.append(body);
    form.append(table);
    if (!data.items.length) form.append(node('p', 'Aún no hay pagos registrados.', 'text-muted'));

    if (data.can_register) {
      const amountLabel = node('label', 'Monto', 'form-label');
      const amount = node('input', undefined, 'form-control mb-2');
      amount.name = 'monto'; amount.type = 'number'; amount.min = '0.01';
      amount.step = '0.01'; amount.required = true;
      const dateLabel = node('label', 'Fecha de pago', 'form-label');
      const date = node('input', undefined, 'form-control mb-2');
      date.name = 'fecha_pago'; date.type = 'date';
      date.value = new Date().toISOString().slice(0, 10); date.required = true;
      const methodLabel = node('label', 'Método', 'form-label');
      const method = node('select', undefined, 'form-select mb-2');
      method.name = 'metodo';
      [
        ['TRANSFERENCIA', 'Transferencia'], ['EFECTIVO', 'Efectivo'],
        ['TARJETA', 'Tarjeta'], ['CHEQUE', 'Cheque'], ['OTRO', 'Otro']
      ].forEach(([value, label]) => {
        const option = node('option', label); option.value = value; method.append(option);
      });
      const referenceLabel = node('label', 'Referencia', 'form-label');
      const reference = node('input', undefined, 'form-control mb-2');
      reference.name = 'referencia';
      const observationsLabel = node('label', 'Observaciones', 'form-label');
      const observations = node('textarea', undefined, 'form-control mb-3');
      observations.name = 'observaciones';
      const submit = node('button', 'Registrar pago', 'btn btn-primary');
      submit.type = 'submit';
      form.append(
        amountLabel, amount, dateLabel, date, methodLabel, method,
        referenceLabel, reference, observationsLabel, observations, submit
      );
      form.onsubmit = async event => {
        event.preventDefault();
        if (!form.reportValidity() || submit.disabled) return;
        submit.disabled = true;
        try {
          const result = await api(
            `documentos-venta/${documento.id}/pagos/`,
            Object.fromEntries(new FormData(form))
          );
          await load('documentos-venta');
          notice(Number(result.saldo) > 0
            ? `Pago parcial registrado. Saldo pendiente: ${formatFinanceAmount(result.saldo)}.`
            : 'Documento saldado. Gracias por registrar el pago.');
          if (current === 'documentos-venta') await openDocumentoPagos(documento);
        } catch (e) {
          notice(e.message, true);
        } finally {
          submit.disabled = false;
        }
      };
    }

    const close = node('button', 'Cerrar', 'btn btn-outline-secondary mt-2');
    close.type = 'button'; close.onclick = () => { $('editor').hidden = true; };
    form.append(close);
    $('editor').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    notice(e.message, true);
  }
}

async function load(resource, filters = activeFilters[resource] || {}, exportFormat = '') {
  const version = ++loadVersion;
  activeFilters[resource] = { ...filters };
  const query = new URLSearchParams(
    Object.entries(activeFilters[resource]).filter(([, value]) => value !== '' && value !== null && value !== undefined)
  );
  const queryString = query.toString();
  const response = await api(`${resource}/${queryString ? `?${queryString}` : ''}`);
  if (version !== loadVersion) return false;
  current = resource;
  metadata = response;
  $('editor').hidden = true;
  $('new').hidden = !metadata.can_write;
  $('dashboard').hidden = true;
  $('module-view').hidden = false;

  $('modules').querySelectorAll('[data-resource]').forEach(button => {
    const active = button.dataset.resource === resource;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  if (typeof setSidebarActive === 'function') setSidebarActive(resource);

  $('section-title').textContent = names[resource] || resource;

  const container = $('records');
  container.replaceChildren();

  if (metadata.notice) {
    const banner = node('div', metadata.notice, 'alert alert-info py-2 mb-3');
    container.append(banner);
  }

  const items = metadata.items || [];
  if (['facturas', 'presupuestos-venta'].includes(resource) && typeof renderSavedCommercial === 'function') {
    renderSavedCommercial(items, container);
  }
  renderFinanceSummary(resource, items, container);
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
  } else if (resource === 'precios') {
    keys = ['articulo_nombre', 'precio_compra', 'precio_lista', 'margen', 'fecha'];
    labels = {articulo_nombre: 'Artículo', precio_compra: 'Compra (CLP)', precio_lista: 'Lista (CLP)', margen: 'Margen sobre venta (%)', fecha: 'Fecha de actualización'};
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
  } else if (resource === 'presupuestos-venta') {
    keys = ['numero', 'cliente_nombre', 'obra_codigo', 'fecha', 'vencimiento', 'estado', 'total'];
    labels = {
      numero: 'N° presupuesto',
      cliente_nombre: 'Cliente',
      obra_codigo: 'OT',
      fecha: 'Fecha',
      vencimiento: 'Vencimiento',
      estado: 'Estado',
      total: 'Total'
    };
  } else if (resource === 'detalles-presupuesto') {
    keys = ['presupuesto_numero', 'articulo_nombre', 'cantidad', 'precio_unitario', 'subtotal'];
    labels = {
      presupuesto_numero: 'Presupuesto',
      articulo_nombre: 'Artículo',
      cantidad: 'Cantidad',
      precio_unitario: 'Precio unitario',
      subtotal: 'Subtotal'
    };
  } else if (resource === 'documentos-venta') {
    keys = ['numero_documento', 'cliente_nombre', 'fecha', 'vencimiento', 'total', 'saldo', 'anulado'];
    labels = {
      numero_documento: 'N° documento',
      cliente_nombre: 'Cliente',
      fecha: 'Fecha',
      vencimiento: 'Vencimiento',
      total: 'Total',
      saldo: 'Saldo',
      anulado: 'Estado'
    };
  } else if (resource === 'notas-credito') {
    keys = ['numero_documento', 'documento_numero', 'fecha', 'motivo', 'monto'];
    labels = {
      numero_documento: 'N° nota de crédito',
      documento_numero: 'Documento original',
      fecha: 'Fecha',
      motivo: 'Motivo',
      monto: 'Monto'
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
  searchInput.value = activeSearch[resource] || '';
  searchGroup.append(searchInput);

  let statusSelect = null;
  if (resource === 'categorias') {
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

  if (canExportResource(resource)) {
    const exportActions = node('div', undefined, 'd-flex flex-wrap gap-2');
    for (const [fileFormat, label, icon] of [
      ['pdf', 'Exportar PDF', 'bi-file-earmark-pdf'],
      ['xlsx', 'Exportar Excel', 'bi-file-earmark-excel']
    ]) {
      const button = node('button', undefined, 'btn btn-sm btn-outline-primary');
      button.type = 'button';
      const glyph = node('i', undefined, `bi ${icon} me-1`);
      glyph.setAttribute('aria-hidden', 'true');
      button.append(glyph, document.createTextNode(label));
      button.onclick = () => exportReport(resource, fileFormat, keys, labels)
        .catch(error => notice(error.message, true));
      exportActions.append(button);
    }
    searchRow.append(exportActions);
  }
  filterBar.append(searchRow);

  const filterFields = metadata.filter_fields || [];
  if (filterFields.length) {
    const advancedFilters = node('div', undefined, 'advanced-filter-grid mt-3');
    const controls = [];
    filterFields.forEach(field => {
      const group = node('label', undefined, 'advanced-filter-field');
      group.append(node('span', field.label, 'form-label mb-1'));
      let input;
      if (field.type === 'select') {
        input = node('select', undefined, 'form-select form-select-sm');
        (field.choices || []).forEach(([value, label]) => {
          const option = node('option', label);
          option.value = value;
          input.append(option);
        });
      } else {
        input = node('input', undefined, 'form-control form-control-sm');
        input.type = field.type === 'date' ? 'date' : 'search';
      }
      input.name = field.name;
      input.value = activeFilters[resource][field.name] || '';
      group.append(input);
      advancedFilters.append(group);
      controls.push(input);
    });

    const filterActions = node('div', undefined, 'advanced-filter-actions');
    const applyButton = node('button', 'Aplicar filtros', 'btn btn-sm btn-primary');
    applyButton.type = 'button';
    applyButton.onclick = () => {
      const next = {};
      controls.forEach(control => {
        if (control.value) next[control.name] = control.value;
      });
      load(resource, next).catch(error => notice(error.message, true));
    };
    const clearButton = node('button', 'Limpiar', 'btn btn-sm btn-outline-secondary');
    clearButton.type = 'button';
    clearButton.onclick = () => load(resource, {}).catch(error => notice(error.message, true));
    filterActions.append(applyButton, clearButton);
    advancedFilters.append(filterActions);
    filterBar.append(advancedFilters);
  }

  container.append(filterBar);
  searchInput.oninput = () => { activeSearch[resource] = searchInput.value; };

  if (!items.length) {
    container.append(node('p', resource === 'solicitudes' ? 'No hay solicitudes registradas.' : 'No hay registros.', 'text-muted'));
    if (exportFormat) await exportReport(resource, exportFormat, keys, labels);
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
      } else if (resource === 'presupuestos-venta' && k === 'estado') {
        td.append(financeStatusBadge(item.estado));
      } else if (k === 'estado') {
        td.append(statusBadge(item.estado));
      } else if (resource === 'documentos-venta' && k === 'anulado') {
        const estado = item.anulado
          ? ['Anulado', 'bg-danger']
          : Number(item.saldo || 0) <= 0
          ? ['Saldado', 'bg-success']
          : Number(item.pagos_count || 0) > 0
          ? ['Pago parcial', 'bg-warning text-dark']
          : ['Pendiente', 'bg-secondary'];
        td.append(node('span', estado[0], `badge finance-status ${estado[1]}`));
      } else if (resource === 'documentos-venta' && k === 'saldo') {
        td.append(
          node('strong', formatFinanceAmount(item.saldo), 'finance-balance'),
          node('span', Number(item.saldo || 0) > 0 ? 'Pendiente' : 'Sin saldo', 'finance-balance-label')
        );
      } else if (k === 'fecha_registro') {
        td.textContent = item[k] ? new Date(item[k]).toLocaleString('es-CL') : '—';
      } else if (['fecha', 'fecha_inicio', 'vencimiento', 'fecha_pago'].includes(k)) {
        td.textContent = item[k] || '—';
      } else if (['monto', 'costo_total_fifo', 'presupuesto_estimado', 'monto_materiales_estimado', 'monto_mano_obra_estimado', 'total_estimado', 'total', 'saldo', 'precio_unitario', 'subtotal'].includes(k)) {
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
    } else if (resource === 'precios' && metadata.can_write) {
      row.append(node('td', 'Histórico: registra un precio nuevo para actualizar.'));
    } else if (resource === 'presupuestos-venta') {
      const actions = node('td');
      if (metadata.can_write) {
        const edit = node('button', 'Editar', 'btn btn-sm btn-outline-primary');
        edit.onclick = async () => {
          try {
            const detail = await api(`${resource}/${item.id}/`);
            showForm(detail.fields, detail.item);
          } catch (e) { notice(e.message, true); }
        };
        actions.append(edit);
      }
      if (metadata.can_approve && item.estado === 'BORRADOR') {
        const approve = node('button', 'Aprobar', 'btn btn-sm btn-success ms-2');
        approve.onclick = () => handlePresupuestoDecision(item, 'aprobar');
        const reject = node('button', 'Rechazar', 'btn btn-sm btn-outline-danger ms-1');
        reject.onclick = () => handlePresupuestoDecision(item, 'rechazar');
        actions.append(approve, reject);
      }
      row.append(actions);
    } else if (resource === 'documentos-venta') {
      const actions = node('td');
      if (metadata.can_write) {
        const edit = node('button', 'Editar', 'btn btn-sm btn-outline-primary');
        edit.onclick = async () => {
          try {
            const detail = await api(`${resource}/${item.id}/`);
            showForm(detail.fields, detail.item);
          } catch (e) { notice(e.message, true); }
        };
        actions.append(edit);
      }
      const payments = node('button', 'Pagos / historial', 'btn btn-sm btn-outline-success ms-1');
      payments.onclick = () => openDocumentoPagos(item);
      actions.append(payments);
      if (metadata.can_void_documents && !item.anulado) {
        const cancel = node('button', 'Anular', 'btn btn-sm btn-outline-danger ms-1');
        cancel.onclick = () => handleDocumentoAnular(item);
        actions.append(cancel);
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
      if (resource === 'facturas' && item.calcular_totales && !item.confirmada && !item.detalles_bloqueados) {
        const confirmButton = node('button', 'Confirmar compra', 'btn btn-sm btn-success ms-2');
        confirmButton.onclick = async () => {
          if (!confirm('¿Confirmar los totales y guardar los precios de lista indicados?')) return;
          confirmButton.disabled = true;
          try { await api(`facturas/${item.id}/confirmar/`, {}); await load('facturas'); notice('Compra confirmada.'); }
          catch(e) { notice(e.message, true); confirmButton.disabled = false; }
        };
        actions.append(confirmButton);
      }
      if (resource === 'facturas' && item.confirmada) {
        actions.append(node('span', 'Confirmada', 'badge bg-success'));
      } else {
        actions.append(b);
      }

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

  searchInput.oninput = () => {
    activeSearch[resource] = searchInput.value;
    applyFilter();
  };
  if (statusSelect) statusSelect.onchange = applyFilter;
  if (exportFormat) await exportReport(resource, exportFormat, keys, labels);
}

function statusBadge(status) {
  const value = String(status || '').toUpperCase();
  const styles = {
    ACTIVO: ['Activo', 'bg-success'],
    ACTIVA: ['Activa', 'bg-success'],
    APROBADO: ['Aprobado', 'bg-success'],
    APROBADA: ['Aprobada', 'bg-success'],
    COMPLETADO: ['Completado', 'bg-success'],
    COMPLETADA: ['Completada', 'bg-success'],
    PENDIENTE: ['Pendiente', 'bg-warning text-dark'],
    PARCIAL: ['Parcial', 'bg-warning text-dark'],
    BORRADOR: ['Borrador', 'bg-warning text-dark'],
    RECHAZADO: ['Rechazado', 'bg-danger'],
    RECHAZADA: ['Rechazada', 'bg-danger'],
    ANULADO: ['Anulado', 'bg-danger'],
    ANULADA: ['Anulada', 'bg-danger']
  };
  const [label, style] = styles[value] || [status || 'Sin estado', 'bg-secondary'];
  return node('span', label, `badge ${style}`);
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
