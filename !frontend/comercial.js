'use strict';

function commercialBreakdown(totals) {
 const list = node('dl', undefined, 'row mb-0');
 const labels = {bruto:'Bruto', descuentos_articulos:'Descuentos por artículo', subtotal:'Subtotal',
  importe_descuento_general:'Descuento general', importe_pronto_pago:'Pronto pago',
  neto:'Neto', impuestos:'IVA', total:'Total'};
 for (const [key, label] of Object.entries(labels)) {
  list.append(node('dt', label, 'col-7'), node('dd', formatFinanceAmount(totals[key]), 'col-5 text-end'));
 }
 return list;
}

function renderSavedCommercial(items, container) {
 const calculated = items.filter(item => item.totales);
 if (!calculated.length) return;
 const details = node('details', undefined, 'mb-3');
 details.append(node('summary', 'Ver totales guardados'));
 for (const item of calculated) {
  const box = node('section', undefined, 'card p-3 my-2');
  box.append(node('h3', item.numero_documento || item.numero, 'h6'), commercialBreakdown(item.totales));
  details.append(box);
 }
 container.append(details);
}

function attachCommercial(form, resource, item, context, invoiceDetails) {
 if (!['facturas', 'presupuestos-venta', 'detalles-presupuesto', 'precios'].includes(resource)) return;
 if (form.commercialController) form.commercialController.abort();
 form.commercialController = new AbortController();
 const eventOptions = {signal: form.commercialController.signal};
 const box = node('section', undefined, 'card p-3 my-3');
 box.setAttribute('aria-live', 'polite');
 const heading = node('h3', resource === 'precios' ? 'Margen calculado' : 'Resumen de totales', 'h6');
 const content = node('div', 'Completa los campos para calcular.');
 box.append(heading, content); form.append(box);
 const field = name => form.elements.namedItem(name);
 const value = (name, initial = '0') => field(name)?.value || initial;
 let timer, sequence = 0;
 if (resource === 'detalles-presupuesto' && field('articulo')) {
  field('articulo').addEventListener('change', () => {
   const price = context.list_prices?.[field('articulo').value];
   if (price !== undefined) field('precio_unitario').value = price;
  });
 }
 async function update() {
  if (!box.isConnected) return;
  const currentSequence = ++sequence;
  if (resource === 'precios') {
   try {
    const response = await api('calculo-comercial/', {precio_compra:value('precio_compra'), precio_lista:value('precio_lista')});
    if (currentSequence === sequence && box.isConnected) content.textContent = `Margen sobre el precio de venta: ${response.margen} %`;
   } catch (error) { if (currentSequence === sequence) content.textContent = error.message; }
   return;
  }
  if (field('calcular_totales') && !field('calcular_totales').checked && !item.calcular_totales) {
   content.textContent = 'Se conservará el monto indicado. Activa el cálculo automático para obtener el desglose.';
   const oldSummary = form.querySelector('.invoice-summary');
   if (oldSummary) oldSummary.hidden = false;
   if (field('monto')) { field('monto').readOnly = false; field('monto').step = '1'; }
   return;
  }
  const lines = resource === 'facturas' ? (invoiceDetails ? invoiceDetails() : item.detalles || [])
   : resource === 'detalles-presupuesto' ? [{cantidad:value('cantidad'), precio_unitario:value('precio_unitario'),
      descuento_1:value('descuento_1'), descuento_2:value('descuento_2'), descuento_3:value('descuento_3')}]
   : item.detalles || [];
  if (!lines.length) { content.textContent = 'Guarda el borrador y agrega sus artículos para calcular los totales.'; return; }
  if (field('monto')) { field('monto').readOnly = true; field('monto').step = '0.01'; }
  const oldSummary = form.querySelector('.invoice-summary');
  if (oldSummary) oldSummary.hidden = true;
  try {
   const response = await api('calculo-comercial/', {detalles:lines,
    descuento_general:value('descuento_general'), descuento_pronto_pago:value('descuento_pronto_pago'),
    tasa_iva:resource === 'detalles-presupuesto' ? '0' : value('tasa_iva', '19')});
   if (currentSequence !== sequence || !box.isConnected) return;
   content.replaceChildren(commercialBreakdown(response.totales));
   if (resource === 'facturas' && invoiceDetails) {
    const rows = [...form.querySelectorAll('.invoice-lines-table tbody tr')].filter(row => !row.hidden);
    response.totales.lineas.forEach((line, index) => {
     const row = rows[index];
     if (row) row.children[row.children.length - 2].textContent = formatFinanceAmount(line.neto_linea);
    });
   }
   if (resource === 'detalles-presupuesto') content.append(node('p', 'Vista de esta línea; los impuestos y descuentos generales se calculan en el presupuesto completo.', 'small text-muted'));
   if (field('monto')) field('monto').value = response.totales.total;
  } catch (error) { if (currentSequence === sequence && box.isConnected) content.textContent = error.message; }
 }
 const schedule = () => { ++sequence; clearTimeout(timer); timer = setTimeout(update, 250); };
 form.addEventListener('input', schedule, eventOptions);
 form.addEventListener('change', schedule, eventOptions);
 form.addEventListener('click', schedule, eventOptions);
 update();
}
