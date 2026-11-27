'use strict';

function logFrontendRequestFailure(resource, endpoint, status) {
 console.error(resource, String(endpoint).split('?')[0], status);
}

function openReportCenter(fileFormat = '') {
 loadVersion++;
 current = 'reportes';
 metadata = null;
 $('dashboard').hidden = true;
 $('module-view').hidden = false;
 $('editor').hidden = true;
 $('new').hidden = true;
 const formatLabel = fileFormat === 'pdf' ? 'PDF' : fileFormat === 'xlsx' ? 'Excel' : '';
 $('section-title').textContent = formatLabel ? `Reportes ${formatLabel}` : 'Reportes';
 $('records').replaceChildren(
  node('p', formatLabel
   ? `Selecciona un conjunto de datos para generar el reporte ${formatLabel}. Se respetarán los permisos de tu rol.`
   : 'Selecciona un módulo. El reporte respetará los filtros visibles y los permisos de tu rol.', 'text-muted')
 );
 if (formatLabel) notify(`Selecciona un conjunto de datos para generar el reporte ${formatLabel}.`, 'info');
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
  button.onclick = () => openModule(resource, fileFormat);
  actions.append(button);
 });
 $('records').append(actions);
}

function canExportResource(resource) {
 if (!user) return false;
 if (user.is_superuser) return true;
 const role = (user.rol || '').toLowerCase();
 if (resource === 'articulos') return true;
 if (['clientes', 'proveedores', 'facturas'].includes(resource)) {
  return role.includes('finanzas') || role.includes('gerencia');
 }
 if (resource === 'kardex') return role.includes('gerencia');
 if (resource === 'obras') {
  return ['gerencia', 'bodega', 'finanzas', 'supervisor', 'obras']
   .some(name => role.includes(name));
 }
 if (resource === 'solicitudes') {
  return ['gerencia', 'bodega', 'supervisor', 'obras']
   .some(name => role.includes(name));
 }
 return false;
}

async function exportReport(resource, fileFormat, keys, labels) {
 beginGlobalLoading();
 notify(`Generando reporte ${fileFormat === 'pdf' ? 'PDF' : 'Excel'}.`, 'warning');
 try {
  const params = new URLSearchParams(
   Object.entries(activeFilters[resource] || {})
    .filter(([, value]) => value !== '' && value !== null && value !== undefined)
  );
  params.set('q', activeSearch[resource] || '');
  params.set('columns', JSON.stringify(keys.map(key => ({
   key,
   label: labels[key] || key.replaceAll('_', ' ').replace(/^./, char => char.toUpperCase())
  }))));
  const endpoint = `${window.API_BASE}/reportes/${resource}/${fileFormat}/?${params.toString()}`;
  let response;
  try {
   response = await fetch(endpoint, { method: 'GET', credentials: 'include' });
  } catch (error) {
   logFrontendRequestFailure(resource, endpoint, null);
   throw error;
  }
  if (!response.ok) {
   logFrontendRequestFailure(resource, endpoint, response.status);
   let body = {};
   try { body = await response.json(); } catch (_) {}
   if (response.status === 401) {
    user = null;
    renderSession();
   }
   const message = response.status >= 500
    ? 'Ha ocurrido un error, intente nuevamente'
    : response.status === 403
    ? 'No posee permisos para acceder'
    : response.status === 401
    ? 'Su sesión ha expirado'
    : body.error || 'No se pudo generar el reporte.';
   throw new Error(message);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = node('a');
  link.href = url;
  link.download = `${resource}.${fileFormat === 'pdf' ? 'pdf' : 'xlsx'}`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  notify(`Reporte ${fileFormat === 'pdf' ? 'PDF' : 'Excel'} descargado correctamente.`, 'success');
 } finally {
  endGlobalLoading();
 }
}
