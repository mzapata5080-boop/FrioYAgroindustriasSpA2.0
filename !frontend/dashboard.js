'use strict';

function goHome() {
 loadVersion++;
 $('dashboard').hidden = false;
 $('module-view').hidden = true;
 $('editor').hidden = true;
 $('notice').replaceChildren();
 current = '';
}

function openModule(resource) {
 load(resource).catch(e => notice(e.message, true));
}

function openReportCenter() {
 loadVersion++;
 current = 'reportes';
 metadata = null;
 $('dashboard').hidden = true;
 $('module-view').hidden = false;
 $('editor').hidden = true;
 $('new').hidden = true;
 $('section-title').textContent = 'Reportes';
 $('records').replaceChildren(
  node('p', 'Selecciona un módulo. El reporte respetará los filtros visibles y los permisos de tu rol.', 'text-muted')
 );
 const actions = node('div', undefined, 'report-center-grid');
 const resources = [
  ['clientes', 'Clientes'],
  ['proveedores', 'Proveedores'],
  ['facturas', 'Facturas'],
  ['articulos', 'Inventario'],
  ['kardex', 'Kardex'],
  ['obras', 'Obras'],
  ['solicitudes', 'Solicitudes']
 ].filter(([resource]) => canExportResource(resource));
 resources.forEach(([resource, title]) => {
  const button = node('button', undefined, 'btn btn-outline-primary report-center-button');
  button.type = 'button';
  const icon = node('i', undefined, `bi ${
   resource === 'clientes' ? 'bi-people' :
   resource === 'proveedores' ? 'bi-truck' :
   resource === 'facturas' ? 'bi-receipt' :
   resource === 'articulos' ? 'bi-box-seam' :
   resource === 'kardex' ? 'bi-clock-history' :
   resource === 'obras' ? 'bi-building' : 'bi-clipboard-check'
  } me-2`);
  icon.setAttribute('aria-hidden', 'true');
  button.append(icon, node('span', title));
  button.onclick = () => openModule(resource);
  actions.append(button);
 });
 $('records').append(actions);
}

function svgElement(name, attributes = {}) {
 const element = document.createElementNS('http://www.w3.org/2000/svg', name);
 Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
 return element;
}

function renderMovementChart(days) {
 const width = 720, height = 220, padding = 24;
 const svg = svgElement('svg', {
  viewBox: `0 0 ${width} ${height}`,
  role: 'img',
  'aria-label': 'Movimientos de inventario por día durante los últimos 30 días'
 });
 const values = days.map(day => Number(day.ingresos || 0) + Number(day.salidas || 0));
 const max = Math.max(...values, 1);
 const coordinates = values.map((value, index) => {
  const x = padding + (index * (width - 2 * padding)) / Math.max(values.length - 1, 1);
  const y = height - padding - (value / max) * (height - 2 * padding);
  return { x, y };
 });
 svg.append(svgElement('line', {
  x1: padding, y1: height - padding, x2: width - padding, y2: height - padding,
  stroke: '#cbd5e1', 'stroke-width': 1
 }));
 for (let index = 1; index <= 2; index++) {
  const y = padding + (index * (height - 2 * padding)) / 3;
  svg.append(svgElement('line', {
   x1: padding, y1: y, x2: width - padding, y2: y,
   stroke: '#e2e8f0', 'stroke-width': 1
  }));
 }
 svg.append(svgElement('polyline', {
  points: coordinates.map(point => `${point.x},${point.y}`).join(' '),
  fill: 'none',
  stroke: '#d97706',
  'stroke-width': 3,
  'stroke-linecap': 'round',
  'stroke-linejoin': 'round'
 }));
 coordinates.forEach(point => svg.append(svgElement('circle', {
  cx: point.x, cy: point.y, r: 2.5, fill: '#9a3412'
 })));
 [0, values.length - 1].forEach(index => {
  if (index < 0 || !days[index]) return;
  const label = svgElement('text', {
   x: coordinates[index].x,
   y: height - 4,
   'text-anchor': index === 0 ? 'start' : 'end',
   fill: '#64748b',
   'font-size': 11
  });
  label.textContent = days[index].fecha.slice(5);
  svg.append(label);
 });
 return svg;
}

function renderIncomeOutcomeChart(days) {
 const width = 720, height = 220, padding = 24;
 const svg = svgElement('svg', {
  viewBox: `0 0 ${width} ${height}`,
  role: 'img',
  'aria-label': 'Comparación de ingresos y salidas de inventario en los últimos 30 días'
 });
 const totals = days.reduce((result, day) => ({
  ingresos: result.ingresos + Number(day.ingresos || 0),
  salidas: result.salidas + Number(day.salidas || 0)
 }), { ingresos: 0, salidas: 0 });
 const max = Math.max(totals.ingresos, totals.salidas, 1);
 const chartHeight = height - 2 * padding;
 const entries = [
  { label: 'Ingresos', value: totals.ingresos, color: '#198754', x: width * .32 },
  { label: 'Salidas', value: totals.salidas, color: '#dc3545', x: width * .58 }
 ];
 entries.forEach(entry => {
  const barHeight = (entry.value / max) * chartHeight;
  const bar = svgElement('rect', {
   x: entry.x, y: height - padding - barHeight, width: 96, height: barHeight,
   rx: 8, fill: entry.color
  });
  svg.append(bar);
  const label = svgElement('text', {
   x: entry.x + 48, y: height - 4, 'text-anchor': 'middle', fill: '#334155',
   'font-size': 14
  });
  label.textContent = `${entry.label}: ${entry.value}`;
  svg.append(label);
 });
 return svg;
}

async function renderManagementDashboard() {
 const section = $('manager-dashboard');
 section.replaceChildren();
 try {
  const dashboard = await api('dashboard/');
  const metrics = [
   ['Total artículos', dashboard.kpis.total_articulos, 'bi-box-seam'],
   ['Stock crítico', dashboard.kpis.stock_critico, 'bi-exclamation-triangle'],
   ['Ingresos mes', dashboard.kpis.ingresos_mes, 'bi-box-arrow-in-down'],
   ['Salidas mes', dashboard.kpis.salidas_mes, 'bi-box-arrow-up'],
   ['Obras activas', dashboard.kpis.obras_activas, 'bi-building'],
   ['Solicitudes pendientes', dashboard.kpis.solicitudes_pendientes, 'bi-clipboard-check'],
   ['Clientes registrados', dashboard.kpis.clientes_registrados, 'bi-people'],
   ['Proveedores registrados', dashboard.kpis.proveedores_registrados, 'bi-truck']
  ];
  const cards = node('div', undefined, 'manager-kpi-grid');
  metrics.forEach(([label, value, icon]) => {
   const card = node('article', undefined, 'card manager-kpi-card');
   const glyph = node('i', undefined, `bi ${icon}`);
   glyph.setAttribute('aria-hidden', 'true');
   card.append(glyph, node('span', label), node('strong', String(value)));
   cards.append(card);
  });

  const charts = node('div', undefined, 'manager-chart-grid');
  const movementCard = node('section', undefined, 'card manager-chart-card');
  movementCard.append(node('h2', 'Movimientos últimos 30 días', 'h5'));
  movementCard.append(renderMovementChart(dashboard.movimientos_30_dias));
  const comparisonCard = node('section', undefined, 'card manager-chart-card');
  comparisonCard.append(node('h2', 'Ingresos vs salidas (30 días)', 'h5'));
  comparisonCard.append(renderIncomeOutcomeChart(dashboard.movimientos_30_dias));
  charts.append(movementCard, comparisonCard);

  const activityCard = node('section', undefined, 'card manager-activity-card');
  activityCard.append(node('h2', 'Últimas actividades Kardex', 'h5'));
  if (!dashboard.actividades_kardex.length) {
   activityCard.append(node('p', 'No hay movimientos registrados.', 'text-muted mb-0'));
  } else {
   const list = node('ul', undefined, 'manager-activity-list');
   dashboard.actividades_kardex.forEach(activity => {
    const row = node('li');
    const title = `${activity.tipo} — ${activity.articulo || 'Artículo'} (${activity.cantidad || 0} ${activity.unidad || ''})`;
    row.append(node('strong', title), node('span', activity.obra || activity.responsable));
    list.append(row);
   });
   activityCard.append(list);
  }
  section.append(cards, charts, activityCard);
 } catch (error) {
  section.replaceChildren(node('p', error.message, 'alert alert-danger'));
 }
}

async function refreshAlerts() {
 if (!user) return;
 const badge = $('alert-count');
 const groupsNode = $('alert-groups');
 try {
  const response = await api('alertas/');
  badge.textContent = response.count > 99 ? '99+' : String(response.count);
  badge.hidden = response.count === 0;
  groupsNode.replaceChildren();
  if (!response.groups.length) {
   groupsNode.append(node('p', 'No hay alertas pendientes.', 'text-muted mb-0'));
   return;
  }
  response.groups.forEach(group => {
   const section = node('section', undefined, 'alert-group');
   const heading = node('h3', undefined, 'h6');
   heading.append(node('span', group.mensaje), node('span', String(group.count), 'badge bg-danger ms-2'));
   section.append(heading);
   const list = node('ul');
   group.items.forEach(item => list.append(node('li', item.nombre)));
   section.append(list);
   const button = node('button', 'Ver registros', 'btn btn-sm btn-outline-primary');
   button.type = 'button';
   button.onclick = () => {
    $('alerts-panel').hidden = true;
    $('alerts-toggle').setAttribute('aria-expanded', 'false');
    load(group.resource, group.filters).catch(error => notice(error.message, true));
   };
   section.append(button);
   groupsNode.append(section);
  });
 } catch (error) {
  groupsNode.replaceChildren(node('p', error.message, 'text-danger mb-0'));
 }
}

function action(resource, label, cls = 'btn-outline-success', create = false) {
 const button = node('button', label, `btn ${cls}`);
 button.type = 'button';
 const icons = {
  trabajadores: 'bi-people',
  clientes: 'bi-person-vcard',
  proveedores: 'bi-truck',
  facturas: 'bi-receipt',
  kardex: 'bi-clock-history',
  obras: 'bi-building',
  presupuestos: 'bi-file-earmark-text',
  solicitudes: 'bi-clipboard-check',
  articulos: 'bi-box-seam',
  ingresos: 'bi-box-arrow-in-down',
  salidas: 'bi-box-arrow-up'
 };
 if (icons[resource]) {
  const icon = node('i', undefined, `bi ${icons[resource]} me-2`);
  icon.setAttribute('aria-hidden', 'true');
  button.append(icon);
 }
 button.onclick = async () => {
  try {
   await load(resource);
   if (create && current === resource && metadata.can_write) {
    showForm(metadata.fields);
   }
  } catch (e) {
   notice(e.message, true);
  }
 };
 return button;
}

function roleCard(title, description, feature, cls, buttons) {
 const card = node('section', undefined, `card role-card ${cls}`);
 card.append(node('h2', title), node('hr'), node('p', description, 'role-description'), node('p', feature, 'role-feature'));
 const actions = node('div', undefined, 'role-actions');
 buttons.forEach(b => actions.append(b));
 card.append(actions);
 return card;
}

function renderSession() {
 $('login-panel').hidden = !!user;
 $('workspace').hidden = !user;
 $('logout').hidden = !user;
 $('identity').textContent = user ? `Bienvenido, ${user.username}` : '';
 $('editor').hidden = true;
 $('records').replaceChildren();
 $('new').hidden = true;
 $('modules').replaceChildren();
 $('role-cards').replaceChildren();
 $('warehouse-actions').replaceChildren();
 $('additional-actions').replaceChildren();
 $('additional-modules').hidden = true;
 $('additional-modules').open = false;
 $('alerts-menu').hidden = !user;
 $('alerts-panel').hidden = true;
 $('manager-dashboard').hidden = true;
 $('manager-dashboard').replaceChildren();

 if (!user) return;

 const userRole = (user.rol || '').toLowerCase();
 const can = roles => user.is_superuser || roles.some(r => userRole.includes(r.toLowerCase()));
 const fullName = (user.name || '').trim();
 $('welcome').textContent = fullName ? `Bienvenido, ${fullName}` : 'Bienvenido,';

 if (can(['gerencia'])) {
  $('manager-dashboard').hidden = false;
  $('role-cards').append(roleCard('Administración y Gerencia', 'Módulo de gestión de personal', 'Agregar nuevos trabajadores y supervisar movimientos', 'management-card', [
   dashboardAction(),
   action('trabajadores', 'Usuarios', 'btn-primary'),
   action('kardex', 'Ver Kardex', 'btn-kardex'),
   action('obras', 'Obras y Proyectos', 'btn-outline-primary'),
   action('presupuestos', 'Presupuestos', 'btn-outline-secondary'),
   reportCenterAction()
  ]));
 }

 const financeButtons = () => [
  action('proveedores', 'Gestión de Proveedores', 'btn-warning'),
  action('clientes', 'Administración de Clientes', 'btn-outline-warning'),
  action('facturas', 'Facturas de Compra', 'btn-outline-warning'),
  action('precios', 'Precios e historial', 'btn-outline-warning'),
  action('presupuestos-venta', 'Presupuestos de Venta', 'btn-outline-secondary'),
  action('detalles-presupuesto', 'Artículos de Presupuestos', 'btn-outline-secondary'),
  action('documentos-venta', 'Pagos y documentos', 'btn-outline-primary'),
  action('notas-credito', 'Notas de Crédito', 'btn-outline-primary'),
  action('presupuestos', 'Presupuestos de Obra', 'btn-outline-secondary'),
  reportCenterAction()
 ];

 if (can(['finanzas']) && !can(['gerencia'])) {
  $('role-cards').append(roleCard('Administrativo y Finanzas', 'Módulo de gestión comercial', 'Administrar clientes, proveedores, presupuestos, documentos y pagos', 'finance-card', financeButtons()));
 } else if (can(['gerencia'])) {
  $('additional-modules').hidden = false;
  financeButtons().forEach(b => $('additional-actions').append(b));
 }

 if (can(['supervisor', 'obras']) && !can(['gerencia', 'bodega'])) {
  $('role-cards').append(roleCard('Supervisión de Obras y Terreno', 'Gestión de obras, presupuestos y requerimientos', 'Crear obras, solicitar materiales y consultar catálogo', 'supervisor-card', [
   action('obras', 'Mis Obras', 'btn-primary'),
   action('obras', 'Nueva Obra', 'btn-outline-primary', true),
   action('presupuestos', 'Presupuestos', 'btn-outline-secondary'),
   action('solicitudes', 'Nueva solicitud', 'btn-success', true),
   action('solicitudes', 'Mis solicitudes', 'btn-outline-success'),
   action('articulos', 'Consultar catálogo', 'btn-outline-secondary')
  ]));
 }

 // Botones de Bodega
 if (can(['bodega', 'gerencia'])) {
  $('warehouse-actions').append(
   action('articulos', 'Abrir inventario', 'btn-outline-primary'),
   action('articulos', 'Crear artículo', 'btn-outline-success', true),
   action('categorias', 'Categorías', 'btn-outline-secondary'),
   action('ingresos', 'Registrar ingreso', 'btn-success', true),
   action('ingresos', 'Ver ingresos', 'btn-outline-success'),
   action('salidas', 'Registrar salida', 'btn-danger', true),
   action('salidas', 'Ver salidas', 'btn-outline-danger'),
   action('solicitudes', 'Solicitudes de obra', 'btn-outline-info'),
   action('obras', 'Obras activas', 'btn-outline-secondary')
  );
  const botonOperaciones = node('button', 'Mermas, devoluciones y correcciones', 'btn btn-outline-danger');
  botonOperaciones.type = 'button';
  botonOperaciones.onclick = abrirOperaciones;
  $('warehouse-actions').append(botonOperaciones);
 } else {
  $('warehouse-actions').append(action('articulos', 'Consultar inventario', 'btn-outline-primary'));
 }

 // Pestañas superiores de navegación por módulo
 for (const [key, title] of Object.entries(names)) {
  let visible = false;
  if (key === 'articulos') {
   visible = true;
  } else if (key === 'trabajadores' || key === 'kardex') {
   visible = can(['gerencia']);
  } else if ([
   'clientes', 'proveedores', 'facturas', 'precios', 'presupuestos-venta',
   'detalles-presupuesto', 'documentos-venta', 'notas-credito'
  ].includes(key)) {
   visible = can(['gerencia', 'finanzas']);
  } else if (['categorias', 'ingresos', 'salidas'].includes(key)) {
   visible = can(['bodega', 'gerencia']);
  } else if (key === 'obras') {
   visible = can(['bodega', 'gerencia', 'finanzas', 'supervisor', 'obras']);
  } else if (key === 'presupuestos') {
   visible = can(['gerencia', 'finanzas', 'supervisor', 'obras']);
  } else if (key === 'solicitudes') {
   visible = can(['bodega', 'gerencia', 'supervisor', 'obras']);
  }

  if (!visible) continue;
  const b = node('button', title, 'btn btn-outline-primary');
  b.type = 'button';
  b.dataset.resource = key;
  b.onclick = () => openModule(key);
  $('modules').append(b);
 }

 goHome();
 $('alerts-menu').hidden = false;
 if (can(['gerencia'])) renderManagementDashboard();
 refreshAlerts();
}

function reportCenterAction() {
 const button = node('button', undefined, 'btn btn-outline-primary');
 button.type = 'button';
 const icon = node('i', undefined, 'bi bi-file-earmark-bar-graph me-2');
 icon.setAttribute('aria-hidden', 'true');
 button.append(icon, document.createTextNode('Reportes'));
 button.onclick = openReportCenter;
 return button;
}

function dashboardAction() {
 const button = node('button', undefined, 'btn btn-outline-primary');
 button.type = 'button';
 const icon = node('i', undefined, 'bi bi-speedometer2 me-2');
 icon.setAttribute('aria-hidden', 'true');
 button.append(icon, node('span', 'Dashboard'));
 button.onclick = () => {
  goHome();
  $('manager-dashboard').scrollIntoView({ behavior: 'smooth', block: 'start' });
 };
 return button;
}

const alertsToggle = $('alerts-toggle');
if (alertsToggle) {
 alertsToggle.onclick = async () => {
  const panel = $('alerts-panel');
  const open = panel.hidden;
  panel.hidden = !open;
  alertsToggle.setAttribute('aria-expanded', String(open));
  if (open) await refreshAlerts();
 };
}
