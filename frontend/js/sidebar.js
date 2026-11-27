'use strict';

function sidebarLink(label, iconName, actionHandler, resource = '') {
 const button = node('button', undefined, 'sidebar-link');
 button.type = 'button';
 button.title = label;
 if (resource) button.dataset.resource = resource;
 else button.dataset.navId = label.toLowerCase();
 const icon = node('i', undefined, `bi ${iconName}`);
 icon.setAttribute('aria-hidden', 'true');
 button.append(icon, node('span', label, 'sidebar-label'));
 button.onclick = actionHandler;
 return button;
}

function buildSidebarNavigation(visibleResources) {
 const nav = $('modules');
 nav.replaceChildren();
 nav.append(sidebarLink('Dashboard', 'bi-speedometer2', () => {
  goHome();
  closeMobileSidebar();
 }));

 const groups = [
  {
   title: 'Inventario', icon: 'bi-box-seam',
   resources: ['articulos', 'categorias', 'ingresos', 'salidas', 'kardex', 'operaciones']
  },
  {
   title: 'Finanzas', icon: 'bi-currency-dollar',
   resources: ['clientes', 'proveedores', 'facturas', 'presupuestos-venta', 'documentos-venta', 'precios', 'detalles-presupuesto', 'notas-credito']
  },
  {
   title: 'Obras', icon: 'bi-building',
   resources: ['obras', 'presupuestos', 'solicitudes']
  },
  {
   title: 'Administración', icon: 'bi-person-gear',
   resources: ['trabajadores']
  }
 ];

 groups.forEach((group, index) => {
  const resources = group.resources.filter(resource => visibleResources.has(resource));
  if (!resources.length) return;
  const section = node('section', undefined, 'sidebar-group');
  const id = `sidebar-submenu-${index}`;
  const toggle = node('button', undefined, 'sidebar-group-toggle');
  toggle.type = 'button';
  toggle.title = group.title;
  toggle.setAttribute('aria-expanded', 'false');
  toggle.setAttribute('aria-controls', id);
  const icon = node('i', undefined, `bi ${group.icon}`);
  icon.setAttribute('aria-hidden', 'true');
  toggle.append(icon, node('span', group.title, 'sidebar-label'));
  const chevron = node('i', undefined, 'bi bi-chevron-down sidebar-chevron');
  chevron.setAttribute('aria-hidden', 'true');
  toggle.append(chevron);

  const submenu = node('div', undefined, 'sidebar-submenu');
  submenu.id = id;
  submenu.hidden = true;
  resources.forEach(resource => {
   const menuLabels = {
    articulos: 'Artículos', ingresos: 'Ingresos', salidas: 'Salidas',
    facturas: 'Facturas', 'presupuestos-venta': 'Presupuestos',
    'documentos-venta': 'Pagos', obras: 'Obras', solicitudes: 'Solicitudes',
    operaciones: 'Mermas, devoluciones y correcciones'
   };
   const label = menuLabels[resource] || names[resource] || resource;
   const icons = {
    articulos: 'bi-box-seam', categorias: 'bi-tags', ingresos: 'bi-box-arrow-in-down',
    salidas: 'bi-box-arrow-up', kardex: 'bi-clock-history', clientes: 'bi-person-vcard',
    proveedores: 'bi-truck', facturas: 'bi-receipt', 'presupuestos-venta': 'bi-file-earmark-text',
    'documentos-venta': 'bi-credit-card', precios: 'bi-currency-dollar',
    'detalles-presupuesto': 'bi-list-check', 'notas-credito': 'bi-receipt-cutoff',
    obras: 'bi-building', presupuestos: 'bi-clipboard-data',
    solicitudes: 'bi-clipboard-check', trabajadores: 'bi-people',
    operaciones: 'bi-arrow-repeat'
   };
   const handler = resource === 'operaciones'
    ? () => abrirOperaciones()
    : () => openModule(resource);
   submenu.append(sidebarLink(label, icons[resource] || 'bi-circle', () => {
    handler();
    closeMobileSidebar();
   }, resource));
  });
  toggle.onclick = () => {
   const expanded = toggle.getAttribute('aria-expanded') !== 'true';
   toggle.setAttribute('aria-expanded', String(expanded));
   submenu.hidden = !expanded;
  };
  section.append(toggle, submenu);
  nav.append(section);
 });

 const reportSection = node('section', undefined, 'sidebar-group');
 const reportToggle = node('button', undefined, 'sidebar-group-toggle');
 reportToggle.type = 'button';
 reportToggle.title = 'Reportes';
 reportToggle.setAttribute('aria-expanded', 'false');
 reportToggle.setAttribute('aria-controls', 'sidebar-reports');
 const reportIcon = node('i', undefined, 'bi bi-bar-chart-line');
 reportIcon.setAttribute('aria-hidden', 'true');
 reportToggle.append(reportIcon, node('span', 'Reportes', 'sidebar-label'));
 const reportChevron = node('i', undefined, 'bi bi-chevron-down sidebar-chevron');
 reportChevron.setAttribute('aria-hidden', 'true');
 reportToggle.append(reportChevron);
 const reportLinks = node('div', undefined, 'sidebar-submenu');
 reportLinks.id = 'sidebar-reports';
 reportLinks.hidden = true;
 [
  ['Dashboard', 'bi-speedometer2', () => goHome()],
  ['PDF', 'bi-file-earmark-pdf', () => openReportCenter('pdf')],
  ['Excel', 'bi-file-earmark-excel', () => openReportCenter('xlsx')]
 ].forEach(([label, iconName, handler]) => {
  const link = sidebarLink(label, iconName, () => {
   handler();
   closeMobileSidebar();
  });
  if (label === 'Dashboard') link.dataset.navId = 'report-dashboard';
  reportLinks.append(link);
 });
 reportToggle.onclick = () => {
  const expanded = reportToggle.getAttribute('aria-expanded') !== 'true';
  reportToggle.setAttribute('aria-expanded', String(expanded));
  reportLinks.hidden = !expanded;
 };
 reportSection.append(reportToggle, reportLinks);
 nav.append(reportSection);
}

function isMobileSidebar() {
 return typeof window !== 'undefined' && window.matchMedia
  ? window.matchMedia('(max-width: 767px)').matches
  : false;
}

function closeMobileSidebar() {
 if (!isMobileSidebar()) return;
 const shell = $('app-shell'), backdrop = $('sidebar-backdrop'), toggle = $('sidebar-toggle');
 if (!shell || !backdrop || !toggle) return;
 shell.classList.remove('mobile-open');
 backdrop.hidden = true;
 toggle.setAttribute('aria-expanded', 'false');
 toggle.setAttribute('aria-label', 'Abrir menú');
 const icon = toggle.querySelector('i');
 if (icon) icon.className = 'bi bi-list';
}

let sidebarInitialized = false;
function setupSidebar() {
 const shell = $('app-shell'), toggle = $('sidebar-toggle'), backdrop = $('sidebar-backdrop');
 if (!shell || !toggle || !backdrop || sidebarInitialized) return;
 sidebarInitialized = true;
 toggle.hidden = false;

 let collapsed = false;
 try {
  collapsed = window.localStorage.getItem('fyag-sidebar-collapsed') === 'true';
 } catch (error) {
  console.warn('No se pudo leer la preferencia del menú lateral.', error);
 }
 shell.classList.toggle('sidebar-collapsed', collapsed);
 toggle.setAttribute('aria-expanded', String(isMobileSidebar() ? false : !collapsed));
 toggle.setAttribute('aria-label', isMobileSidebar() ? 'Abrir menú' : collapsed ? 'Expandir menú' : 'Contraer menú');

 toggle.onclick = () => {
  if (isMobileSidebar()) {
   const open = !shell.classList.contains('mobile-open');
   shell.classList.toggle('mobile-open', open);
   backdrop.hidden = !open;
   toggle.setAttribute('aria-expanded', String(open));
   toggle.setAttribute('aria-label', open ? 'Cerrar menú' : 'Abrir menú');
   const icon = toggle.querySelector('i');
   if (icon) icon.className = open ? 'bi bi-x-lg' : 'bi bi-list';
   return;
  }
  collapsed = !shell.classList.contains('sidebar-collapsed');
  shell.classList.toggle('sidebar-collapsed', collapsed);
  toggle.setAttribute('aria-expanded', String(!collapsed));
  toggle.setAttribute('aria-label', collapsed ? 'Expandir menú' : 'Contraer menú');
  const icon = toggle.querySelector('i');
  if (icon) icon.className = 'bi bi-list';
  try {
   window.localStorage.setItem('fyag-sidebar-collapsed', String(collapsed));
  } catch (error) {
   console.warn('No se pudo guardar la preferencia del menú lateral.', error);
  }
 };
 backdrop.onclick = closeMobileSidebar;
 window.addEventListener('resize', () => {
  if (isMobileSidebar() || !shell.classList.contains('mobile-open')) return;
  shell.classList.remove('mobile-open');
  backdrop.hidden = true;
  toggle.setAttribute('aria-expanded', String(!collapsed));
  toggle.setAttribute('aria-label', collapsed ? 'Expandir menú' : 'Contraer menú');
  const icon = toggle.querySelector('i');
  if (icon) icon.className = 'bi bi-list';
 });
}

function setSidebarActive(resource) {
 if (typeof document === 'undefined') return;
 document.querySelectorAll('#modules [data-resource], #modules [data-nav-id]').forEach(link => {
  const active = resource
   ? link.dataset.resource === resource
   : link.dataset.navId === 'dashboard';
  link.classList.toggle('active', active);
  if (active) link.setAttribute('aria-current', 'page');
  else link.removeAttribute('aria-current');
 });
}
