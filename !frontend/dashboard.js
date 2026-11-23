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

function action(resource, label, cls = 'btn-outline-success', create = false) {
 const button = node('button', label, `btn ${cls}`);
 button.type = 'button';
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

 if (!user) return;

 const userRole = (user.rol || '').toLowerCase();
 const can = roles => user.is_superuser || roles.some(r => userRole.includes(r.toLowerCase()));
 const fullName = (user.name || '').trim();
 $('welcome').textContent = fullName ? `Bienvenido, ${fullName}` : 'Bienvenido,';

 if (can(['gerencia'])) {
  $('role-cards').append(roleCard('Administración y Gerencia', 'Módulo de gestión de personal', 'Agregar nuevos trabajadores y supervisar movimientos', 'management-card', [
   action('trabajadores', 'Gestionar Trabajadores', 'btn-primary'),
   action('kardex', 'Ver Kardex', 'btn-kardex'),
   action('obras', 'Obras y Proyectos', 'btn-outline-primary'),
   action('presupuestos', 'Presupuestos', 'btn-outline-secondary')
  ]));
 }

 const financeButtons = () => [
  action('proveedores', 'Gestión de Proveedores', 'btn-warning'),
  action('clientes', 'Administración de Clientes', 'btn-outline-warning'),
  action('facturas', 'Facturas de Compra', 'btn-outline-warning'),
  action('presupuestos-venta', 'Presupuestos de Venta', 'btn-outline-secondary'),
  action('detalles-presupuesto', 'Artículos de Presupuestos', 'btn-outline-secondary'),
  action('documentos-venta', 'Documentos de Venta', 'btn-outline-primary'),
  action('notas-credito', 'Notas de Crédito', 'btn-outline-primary'),
  action('presupuestos', 'Presupuestos de Obra', 'btn-outline-secondary')
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
   'clientes', 'proveedores', 'facturas', 'presupuestos-venta',
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
}
