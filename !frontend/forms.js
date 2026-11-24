'use strict';

function requestId() {
 if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
 const cryptoObj = window.crypto || (typeof webcrypto !== 'undefined' ? webcrypto : null);
 if (cryptoObj && cryptoObj.getRandomValues) {
  const bytes = cryptoObj.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
 }
 return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
  const r = Math.random() * 16 | 0;
  return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
 });
}

function searchableSelect(select, label, wrapper) {
 const search = node('input'); search.type = 'search'; search.className = 'form-control mb-2';
 search.placeholder = `Buscar ${label.toLowerCase()}`;
 search.setAttribute('aria-label', `Buscar ${label.toLowerCase()}`);
 const hint = node('p', '', 'small text-muted'); hint.setAttribute('aria-live', 'polite');
 const choices = [...select.options].map(o => ({ value: o.value, text: o.textContent }));
 const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

 search.oninput = () => {
  const text = normalize(search.value.trim());
  const matches = choices.filter(o => o.value && normalize(o.text).includes(text));
  select.replaceChildren();
  const empty = node('option', 'Selecciona una opción'); empty.value = ''; select.append(empty);
  matches.forEach(o => { const option = node('option', o.text); option.value = o.value; select.append(option); });
  select.value = ''; select.size = text ? Math.min(6, Math.max(2, matches.length + 1)) : 1;
  hint.textContent = matches.length ? `${matches.length} coincidencia(s). Selecciona una opción.` : 'No hay coincidencias.';
  select.dispatchEvent(new Event('change'));
 };
 select.addEventListener('change', () => { if (select.value) select.size = 1; });
 wrapper.append(search); return hint;
}

function scaledAmount(value) {
 const text = String(value).trim().replace(',', '.');
 if (!/^\d+(\.\d{1,2})?$/.test(text)) return null;
 const [whole, part = ''] = text.split('.');
 return BigInt(whole) * 100n + BigInt(part.padEnd(2, '0'));
}

function formatCents(cents) {
 const whole = (cents / 100n).toLocaleString('es-CL');
 const fraction = cents % 100n;
 return `$${whole}${fraction ? `,${fraction.toString().padStart(2, '0')}` : ''} CLP`;
}

function formatSubtotal(quantity, price) {
 const q = scaledAmount(quantity), p = scaledAmount(price);
 if (q === null || p === null) return '—';
 const cents = (q * p + 50n) / 100n;
 return formatCents(cents);
}

function allowExistingFraction(input, value) {
 const amount = scaledAmount(value);
 if (amount !== null && amount % 100n !== 0n) input.step = '0.01';
}

function attachReceiptDetails(form, context) {
 const invoice = form.elements.namedItem('factura');
 const availableLines = context.invoiceDetails || [];
 const section = node('section', undefined, 'mb-3');
 const heading = node('h3', 'Artículos recibidos', 'h5');
 const rowsContainer = node('div');
 rowsContainer.id = 'receipt-details-list';
 const rows = [];
 const addButton = node('button', 'Agregar otro artículo', 'btn btn-outline-primary btn-sm mt-2');
 addButton.type = 'button';

 function addRow() {
  const index = rows.length + 1;
  const row = node('div', undefined, 'row g-2 align-items-end border rounded p-2 mb-2');
  const lineWrap = node('div', undefined, 'col-md-8');
  const lineLabel = node('label', 'Artículo pendiente', 'form-label');
  const lineSelect = node('select');
  lineSelect.className = 'form-select';
  lineSelect.required = true;
  lineLabel.htmlFor = `receipt-detail-line-${index}`;
  lineSelect.id = lineLabel.htmlFor;
  lineWrap.append(lineLabel, lineSelect);

  const quantityWrap = node('div', undefined, 'col-md-2');
  const quantityLabel = node('label', 'Cantidad recibida', 'form-label');
  const quantity = node('input');
  quantity.type = 'number';
  quantity.className = 'form-control';
  quantity.required = true;
  quantityLabel.htmlFor = `receipt-detail-quantity-${index}`;
  quantity.id = quantityLabel.htmlFor;
  quantityWrap.append(quantityLabel, quantity);

  const actionWrap = node('div', undefined, 'col-md-2');
  const removeButton = node('button', 'Quitar', 'btn btn-outline-danger w-100');
  removeButton.type = 'button';
  removeButton.onclick = () => { row.hidden = true; };
  actionWrap.append(removeButton);

  function updateLineOptions() {
   const selected = lineSelect.value;
   lineSelect.replaceChildren();
   const placeholder = node('option', 'Selecciona un artículo');
   placeholder.value = '';
   lineSelect.append(placeholder);
   availableLines
    .filter(line => String(line.factura_id) === invoice.value)
    .forEach(line => {
     const option = node(
      'option',
      `${line.codigo_parte} — ${line.articulo_nombre} (pendiente: ${line.pendiente})`
     );
     option.value = String(line.id);
     lineSelect.append(option);
    });
   lineSelect.value = [...lineSelect.options].some(option => option.value === selected)
    ? selected
    : '';
   updateQuantityLimit();
  }

  function updateQuantityLimit() {
   const line = availableLines.find(item => String(item.id) === lineSelect.value);
   if (!line) {
    quantity.value = '';
    quantity.max = '';
    quantity.min = '0.01';
    quantity.step = '0.01';
    quantityLabel.textContent = 'Cantidad recibida';
    return;
   }
   quantity.max = line.pendiente;
   quantity.min = line.unidad_medida === 'unidad' ? '1' : '0.01';
   quantity.step = line.unidad_medida === 'unidad' ? '1' : '0.01';
   quantityLabel.textContent = `Cantidad recibida (${line.unidad_medida})`;
  }

  lineSelect.addEventListener('change', updateQuantityLimit);
  row.append(lineWrap, quantityWrap, actionWrap);
  rowsContainer.append(row);
  rows.push({ row, lineSelect, quantity, updateLineOptions });
  updateLineOptions();
 }

 invoice.addEventListener('change', () => rows.forEach(row => row.updateLineOptions()));
 addRow();
 addButton.onclick = addRow;
 section.append(heading, rowsContainer, addButton);
 form.append(section);

 return () => rows
  .filter(entry => !entry.row.hidden)
  .map(entry => ({
   detalle_factura: entry.lineSelect.value,
   cantidad: entry.quantity.value
  }));
}

function attachInvoiceDetails(form, context, initialDetails, allowEmpty = false, locked = false) {
 const articles = context.articles || [];
 const articleById = new Map(articles.map(article => [String(article.id), article]));
 const units = { unidad: 'Unidades', m: 'Metros', kg: 'Kilogramos', l: 'Litros' };
 const section = node('section', undefined, 'mb-3');
 const heading = node('h3', 'Artículos de la factura', 'h5');
 const rowsContainer = node('div', undefined, 'table-responsive invoice-lines-wrap');
 rowsContainer.id = 'invoice-details-list';
 const rows = [];
 const addButton = node('button', 'Agregar artículo', 'btn btn-outline-primary btn-sm mt-2');
 addButton.type = 'button';

 if (locked) {
  const notice = node(
   'p',
   'Los artículos de esta factura están bloqueados porque ya hay cantidades recibidas.',
   'text-muted'
  );
  const details = initialDetails || [];
  if (details.length) {
   const table = node('table', undefined, 'table table-sm table-bordered align-middle');
   const head = node('thead'), headerRow = node('tr');
   ['Artículo', 'Cantidad facturada', 'Precio unitario'].forEach(title => {
    headerRow.append(node('th', title));
   });
   head.append(headerRow);
   const body = node('tbody');
   details.forEach(detail => {
    const row = node('tr');
    const price = scaledAmount(detail.precio_unitario);
    [detail.articulo_nombre, detail.cantidad, price === null
      ? detail.precio_unitario
      : formatCents(price)].forEach(value => {
     row.append(node('td', String(value ?? '—')));
    });
    body.append(row);
   });
   table.append(head, body);
   rowsContainer.append(table);
  } else {
   rowsContainer.append(node(
    'p',
    'No se encontraron líneas de artículos para mostrar en esta factura.',
    'text-muted'
   ));
  }
  section.append(heading, notice, rowsContainer);
  form.append(section);
  return null;
 }

 const table = node('table', undefined, 'table table-bordered align-middle invoice-lines-table');
 const head = node('thead'), headerRow = node('tr');
 ['Artículo', 'Cantidad', 'Precio unitario', 'D1 %', 'D2 %', 'D3 %', 'Precio lista', 'Subtotal', ''].forEach(title => {
  headerRow.append(node('th', title));
 });
 head.append(headerRow);
 const body = node('tbody');
 table.append(head, body);
 rowsContainer.append(table);

 const amount = form.elements.namedItem('monto');
 const subtotalValue = node('strong', '$0,00 CLP');
 const amountValue = node('strong', '—');
 const summary = node('div', undefined, 'invoice-summary');
 const subtotalRow = node('div', undefined, 'invoice-summary-row');
 subtotalRow.append(node('span', 'Bruto de artículos (antes de descuentos)'), subtotalValue);
 const amountRow = node('div', undefined, 'invoice-summary-row');
 amountRow.append(node('span', 'Monto indicado en factura'), amountValue);
 summary.append(subtotalRow, amountRow);

 function updateSummary() {
  let total = 0n;
  rows.forEach(entry => {
   const quantity = scaledAmount(entry.quantity.value);
   const price = scaledAmount(entry.price.value);
   if (entry.row.hidden || quantity === null || price === null) {
    entry.lineSubtotal.textContent = '—';
    return;
   }
   const lineTotal = (quantity * price + 50n) / 100n;
   total += lineTotal;
   entry.lineSubtotal.textContent = formatSubtotal(entry.quantity.value, entry.price.value);
  });
  subtotalValue.textContent = formatCents(total);
  amountValue.textContent = amount && amount.value ? formatSubtotal('1', amount.value) : '—';
 }

 function addRow(detail = {}) {
  const index = rows.length + 1;
  const row = node('tr');
  const articleCell = node('td');
  const articleLabel = node('label', 'Artículo', 'visually-hidden');
  const articleSelect = node('select');
  articleSelect.className = 'form-select';
  articleSelect.required = true;
  const placeholder = node('option', 'Selecciona un artículo');
  placeholder.value = '';
  articleSelect.append(placeholder);
  articles.forEach(article => {
   const option = node('option', `${article.codigo_parte} — ${article.descripcion}`);
   option.value = String(article.id);
   articleSelect.append(option);
  });
  articleSelect.value = String(detail.articulo ?? detail.articulo_id ?? '');
  articleLabel.htmlFor = `invoice-detail-article-${index}`;
  articleSelect.id = articleLabel.htmlFor;
  articleCell.append(articleLabel, articleSelect);

  const quantityCell = node('td');
  const quantityLabel = node('label', 'Cantidad', 'visually-hidden');
  const quantity = node('input');
  quantity.type = 'number';
  quantity.className = 'form-control';
  quantity.min = '0.01';
  quantity.step = '0.01';
  quantity.required = true;
  quantity.value = detail.cantidad ?? '';
  quantityLabel.htmlFor = `invoice-detail-quantity-${index}`;
  quantity.id = quantityLabel.htmlFor;
  quantityCell.append(quantityLabel, quantity);

  const priceCell = node('td');
  const priceLabel = node('label', 'Precio unitario', 'visually-hidden');
  const price = node('input');
  price.type = 'number';
  price.className = 'form-control';
  price.min = '0';
  price.step = '0.01';
  price.required = true;
  price.value = detail.precio_unitario ?? '';
  allowExistingFraction(price, detail.precio_unitario);
  priceLabel.htmlFor = `invoice-detail-price-${index}`;
  price.id = priceLabel.htmlFor;
  priceCell.append(priceLabel, price);

  const discountInputs = [1, 2, 3].map(n => {
   const input = node('input'); input.type = 'number'; input.min = '0'; input.max = '100';
   input.step = '0.01'; input.value = detail[`descuento_${n}`] ?? '0'; input.className = 'form-control';
   input.setAttribute('aria-label', `Descuento ${n} (%)`); return input;
  });
  const listPrice = node('input'); listPrice.type = 'number'; listPrice.min = '0.01'; listPrice.step = '0.01';
  listPrice.value = detail.precio_lista ?? ''; listPrice.className = 'form-control';
  listPrice.setAttribute('aria-label', 'Precio de lista (CLP)');
  const extraCells = [...discountInputs, listPrice].map(input => { const cell = node('td'); cell.append(input); return cell; });
  const lineSubtotal = node('td', '—', 'text-end text-nowrap');
  const actionCell = node('td');
  const removeButton = node('button', 'Quitar', 'btn btn-outline-danger w-100');
  removeButton.type = 'button';
  removeButton.onclick = () => { row.hidden = true; updateSummary(); };
  actionCell.append(removeButton);

  function updateQuantityStep() {
   const article = articleById.get(articleSelect.value);
   quantity.step = article && article.unidad_medida === 'unidad' ? '1' : '0.01';
   quantity.min = article && article.unidad_medida === 'unidad' ? '1' : '0.01';
   const unit = article ? (units[article.unidad_medida] || article.unidad_medida) : '';
   quantityLabel.textContent = unit ? `Cantidad (${unit})` : 'Cantidad';
  }
  articleSelect.addEventListener('change', updateQuantityStep);
  quantity.addEventListener('input', updateSummary);
  price.addEventListener('input', updateSummary);
  updateQuantityStep();

  row.append(articleCell, quantityCell, priceCell, ...extraCells, lineSubtotal, actionCell);
  body.append(row);
  rows.push({ id: detail.id, row, articleSelect, quantity, price, lineSubtotal, discountInputs, listPrice });
  updateSummary();
 }

 if (initialDetails && initialDetails.length) initialDetails.forEach(addRow);
 else if (!allowEmpty) addRow();
 addButton.onclick = () => addRow();
 if (amount) amount.addEventListener('input', updateSummary);
 updateSummary();
 section.append(heading, rowsContainer, addButton, summary);
 form.append(section);

 return () => rows
  .filter(entry => !entry.row.hidden)
  .map(entry => ({
   ...(entry.id ? { id: entry.id } : {}),
   articulo: entry.articleSelect.value,
   cantidad: entry.quantity.value,
   precio_unitario: entry.price.value,
   descuento_1: entry.discountInputs[0].value || '0',
   descuento_2: entry.discountInputs[1].value || '0',
   descuento_3: entry.discountInputs[2].value || '0',
   precio_lista: entry.listPrice.value
  }));
}

function attachOutputDetails(form, context) {
 const articles = new Map((context.articles || []).map(a => [String(a.id), a]));
 const units = { unidad: 'Unidades', m: 'Metros', kg: 'Kilogramos', l: 'Litros' };
 const article = form.elements.namedItem('articulo');
 const qty = form.elements.namedItem('cantidad');
 const solMat = form.elements.namedItem('solicitud_material');
 const work = form.elements.namedItem('obra');
 const client = form.elements.namedItem('cliente');
 const workOrder = form.elements.namedItem('numero_ot');
 const works = new Map((context.works || []).map(item => [String(item.id), item]));
 const materialRequests = new Map((context.materialRequests || [])
  .map(item => [String(item.id), item]));
 const materialRequest = form.elements.namedItem('solicitud_material');
 if (!article || !qty) return;

 const box = node('div', undefined, 'mb-3');
 const unit = node('input'); unit.readOnly = true; unit.className = 'form-control'; unit.id = 'output-unit';
 const label = node('label', 'Unidad del artículo', 'form-label'); label.htmlFor = unit.id;
 const stockNotice = node('p', '', 'small fw-semibold mt-1'); stockNotice.setAttribute('aria-live', 'polite');
 box.append(label, unit, stockNotice);

 const qtyWrap = qty.closest ? qty.closest('.mb-3') : null;
 if (qtyWrap && qtyWrap.parentNode) {
  qtyWrap.parentNode.insertBefore(box, qtyWrap);
 } else {
  form.append(box);
 }

 function update() {
  const item = articles.get(article.value);
  if (!item) {
   unit.value = 'Selecciona un artículo';
   stockNotice.textContent = '';
   stockNotice.className = 'small fw-semibold mt-1 text-muted';
   return;
  }
  const code = item.unidad_medida;
  const unitLabel = units[code] || code;
  unit.value = unitLabel;
  const stockFisico = Number(item.stock_actual || 0);
  const stockReservado = Number(item.stock_reservado || 0);
  const hasSolicitud = !!(solMat && solMat.value);
  const maxAllowed = hasSolicitud ? stockFisico : Math.max(0, stockFisico - stockReservado);

  qty.step = code === 'unidad' ? '1' : '0.01';
  qty.min = code === 'unidad' ? '1' : '0.01';
  qty.max = String(maxAllowed);

  if (maxAllowed <= 0) {
   stockNotice.textContent = `Sin existencias disponibles para despacho libre (Físico: ${stockFisico}, Reservado: ${stockReservado} ${unitLabel}).`;
   stockNotice.className = 'small fw-semibold mt-1 text-danger';
  } else {
   stockNotice.textContent = hasSolicitud
    ? `Despacho con reserva aprobada (Stock físico en bodega: ${stockFisico} ${unitLabel})`
    : `Stock disponible libre: ${maxAllowed} ${unitLabel} (Físico: ${stockFisico}, Reservado: ${stockReservado})`;
   stockNotice.className = 'small fw-semibold mt-1 text-success';
  }

  const entered = Number(qty.value || 0);
  if (entered > maxAllowed) {
   stockNotice.textContent = `La cantidad (${entered}) supera el máximo permitido (${maxAllowed} ${unitLabel}).`;
   stockNotice.className = 'small fw-semibold mt-1 text-danger';
  }
 }
 article.addEventListener('change', update);
 qty.addEventListener('input', update);
 if (solMat) solMat.addEventListener('change', update);

 if (work) {
  work.addEventListener('change', () => {
   const selectedWork = works.get(work.value);
   if (!selectedWork) return;
   if (client) {
    client.value = String(selectedWork.cliente_id);
    client.dispatchEvent(new Event('change'));
   }
   if (workOrder) workOrder.value = selectedWork.codigo_ot;
  });
 }

 if (materialRequest) {
  materialRequest.addEventListener('change', () => {
   const selectedRequest = materialRequests.get(materialRequest.value);
   if (!selectedRequest) return;
   if (work) {
    work.value = String(selectedRequest.obra_id);
    work.dispatchEvent(new Event('change'));
   }
   article.value = String(selectedRequest.articulo_id);
   article.dispatchEvent(new Event('change'));
   qty.value = selectedRequest.cantidad_pendiente;
   qty.dispatchEvent(new Event('input'));
  });
 }

 update();
}

function attachSolicitudDetails(form, context) {
 const articles = new Map((context.articles || []).map(a => [String(a.id), a]));
 const units = { unidad: 'Unidades', m: 'Metros', kg: 'Kilogramos', l: 'Litros' };
 const article = form.elements.namedItem('articulo');
 const qty = form.elements.namedItem('cantidad_solicitada') || form.elements.namedItem('cantidad');
 if (!article || !qty) return;

 const box = node('div', undefined, 'mb-3');
 const unit = node('input'); unit.readOnly = true; unit.className = 'form-control'; unit.id = 'solicitud-unit';
 const label = node('label', 'Unidad de medida requerida', 'form-label'); label.htmlFor = unit.id;
 const stockHint = node('p', '', 'small text-muted mt-1');
 box.append(label, unit, stockHint);

 const qtyWrap = qty.closest ? qty.closest('.mb-3') : null;
 if (qtyWrap && qtyWrap.parentNode) {
  qtyWrap.parentNode.insertBefore(box, qtyWrap);
 } else {
  form.append(box);
 }

 function update() {
  const item = articles.get(article.value);
  if (!item) {
   unit.value = 'Selecciona un artículo';
   stockHint.textContent = '';
   return;
  }
  const code = item.unidad_medida;
  const unitLabel = units[code] || code;
  unit.value = unitLabel;
  qty.step = code === 'unidad' ? '1' : '0.01';
  qty.min = code === 'unidad' ? '1' : '0.01';
  const disp = Math.max(0, Number(item.stock_actual || 0) - Number(item.stock_reservado || 0));
  stockHint.textContent = `Stock libre actual en bodega: ${disp} ${unitLabel}`;
 }
 article.addEventListener('change', update);
 update();
}

function showForm(fields, item = {}) {
 const resource = current, editId = item.id || null, context = metadata;
 $('editor').hidden = false;

 const titles = {
  articulos: editId ? 'Editar artículo' : 'Crear artículo',
  categorias: editId ? 'Editar categoría' : 'Nueva categoría',
  facturas: editId ? 'Editar factura de compra' : 'Registrar factura de compra',
  'presupuestos-venta': editId ? 'Editar presupuesto de venta' : 'Nuevo presupuesto de venta',
  'detalles-presupuesto': editId ? 'Editar artículo de presupuesto' : 'Agregar artículo al presupuesto',
  precios: 'Registrar nuevo precio (conserva historial)',
  'documentos-venta': editId ? 'Editar documento de venta' : 'Nuevo documento de venta',
  'notas-credito': editId ? 'Editar nota de crédito' : 'Registrar nota de crédito',
  ingresos: 'Registrar ingreso',
  salidas: 'Registrar salida de bodega',
  obras: editId ? 'Editar obra' : 'Nueva obra / proyecto',
  presupuestos: editId ? 'Editar presupuesto' : 'Nuevo presupuesto de obra',
  solicitudes: 'Nueva solicitud de materiales'
 };
 $('editor-title').textContent = titles[resource] || (editId ? 'Editar registro' : 'Nuevo registro');

 const form = $('edit-form');
 form.replaceChildren();
 let invoiceFieldsGrid = null;
 if (resource === 'facturas') {
  const invoiceHeader = node('section', undefined, 'invoice-entry-header mb-4');
  invoiceFieldsGrid = node('div', undefined, 'invoice-fields-grid');
  invoiceHeader.append(node('h3', 'Datos del documento', 'h5'), invoiceFieldsGrid);
  form.append(invoiceHeader);
 }

 for (const field of fields) {
  const wrap = node('div', undefined, 'mb-3'), id = `field-${field.name}`;
  let input;

  if (field.type === 'select') {
   input = node('select');
   if (field.multiple) input.multiple = true;
   field.choices.forEach(([value, label]) => {
    const option = node('option', label);
    option.value = value;
    input.append(option);
   });
  } else if (field.type === 'textarea') {
   input = node('textarea');
  } else if (field.type === 'details' || field.type === 'receipt_details') {
   continue;
  } else {
   input = node('input');
   input.type = field.type;
   if (field.type === 'number') input.step = field.step || '0.01';
  }

  input.name = field.name;
  input.id = id;
  input.required = field.required;
  input.className = field.type === 'checkbox' ? 'form-check-input' : 'form-control';
  if (field.maxLength) input.maxLength = field.maxLength;
  if (field.min !== undefined) input.min = field.min;
  if (field.max !== undefined) input.max = field.max;

  if (field.type === 'checkbox') {
   input.checked = item[field.name] !== undefined ? !!item[field.name] : true;
  } else if (input.multiple && Array.isArray(item[field.name])) {
   const selected = new Set(item[field.name].map(String));
   [...input.options].forEach(opt => { opt.selected = selected.has(opt.value); });
  } else {
   input.value = item[field.name] ?? (field.name === 'solicitud_id' ? requestId() : (field.initial ?? ''));
   if (field.type === 'number' && field.step === '1') {
    allowExistingFraction(input, item[field.name]);
   }
  }

  if (field.type === 'hidden') {
   wrap.hidden = true;
  } else {
   const label = node('label', field.label, 'form-label');
   label.htmlFor = id;
   wrap.append(label);
  }
  if (resource === 'facturas' && field.name === 'observaciones') {
   wrap.className += ' invoice-field-wide';
  }

  let hint;
  if (['ingresos', 'salidas', 'solicitudes'].includes(resource) && ['factura', 'articulo', 'obra'].includes(field.name) && !input.multiple) {
   hint = searchableSelect(input, field.label, wrap);
  }

  if (resource === 'obras' && field.name === 'tecnicos' && input.multiple) {
   input.hidden = true;
   const picker = node('div', undefined, 'technician-picker');
   const toggle = node('button', 'Seleccionar técnicos', 'btn btn-outline-secondary w-100 text-start');
   toggle.type = 'button';
   toggle.setAttribute('aria-expanded', 'false');
   toggle.setAttribute('aria-controls', `${id}-choices`);
   const menu = node('div', undefined, 'technician-picker-menu');
   menu.id = `${id}-choices`;
   menu.hidden = true;
   menu.setAttribute('role', 'group');
   menu.setAttribute('aria-label', 'Técnicos disponibles');
   const selectedTitle = node('p', 'Técnicos seleccionados:', 'form-text mb-1 mt-2');
   const selectedList = node('ol', undefined, 'technician-selected-list mb-1');
   const emptySelection = node('p', 'Ningún técnico seleccionado.', 'form-text mb-0');

   [...input.options].forEach(option => {
    if (!option.value) return;
    const optionLabel = node('label', undefined, 'technician-picker-option');
    const checkbox = node('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'form-check-input';
    checkbox.value = option.value;
    checkbox.checked = option.selected;
    checkbox.onchange = () => {
     option.selected = checkbox.checked;
     updateSelected();
    };
    optionLabel.append(checkbox, node('span', option.textContent));
    menu.append(optionLabel);
   });

   function updateSelected() {
    const selected = [...input.options].filter(option => option.selected);
    selectedList.replaceChildren(...selected.map(option => node('li', option.textContent)));
    emptySelection.hidden = selected.length > 0;
    toggle.textContent = selected.length
     ? `Seleccionar técnicos (${selected.length} seleccionados)`
     : 'Seleccionar técnicos';
   }

   toggle.onclick = () => {
    menu.hidden = !menu.hidden;
    toggle.setAttribute('aria-expanded', String(!menu.hidden));
   };
   updateSelected();
   picker.append(toggle, menu);
   wrap.append(picker, selectedTitle, selectedList, emptySelection, input);
  } else {
   wrap.append(input);
  }
  if (hint) wrap.append(hint);
  if (invoiceFieldsGrid) invoiceFieldsGrid.append(wrap);
  else form.append(wrap);
 }

 const invoiceDetails = resource === 'facturas'
  ? attachInvoiceDetails(
   form,
   context,
   item.detalles,
   Boolean(editId && !item.detalles.length),
   Boolean(item.detalles_bloqueados)
  )
  : null;
 const receiptDetails = resource === 'ingresos'
  ? attachReceiptDetails(form, context)
  : null;

 if (typeof attachCommercial === 'function') attachCommercial(form, resource, item, context, invoiceDetails);
 if (resource === 'salidas') attachOutputDetails(form, context);
 if (resource === 'solicitudes') attachSolicitudDetails(form, context);

 const buttonLabels = {
  ingresos: 'Confirmar ingreso',
  salidas: 'Confirmar salida',
  solicitudes: 'Enviar solicitud'
 };
 const submit = node('button', buttonLabels[resource] || 'Guardar', 'btn btn-primary');
 submit.type = 'submit';

 const cancel = node('button', 'Cancelar', 'btn btn-outline-secondary ms-2');
 cancel.type = 'button';
 cancel.onclick = () => { $('editor').hidden = true; };

 form.append(submit, cancel);

 let submitting = false;
 form.onsubmit = async event => {
  event.preventDefault();
  if (submitting) return;
  submitting = true;
  submit.disabled = true;

  const payload = {};
  fields.forEach(f => {
   if (f.type === 'details' || f.type === 'receipt_details') return;
   const input = form.elements.namedItem(f.name);
   if (input && input.multiple) {
    payload[f.name] = [...input.selectedOptions].map(opt => opt.value);
   } else {
    payload[f.name] = f.type === 'checkbox' ? input.checked : input.value;
   }
  });
  if (invoiceDetails) payload.detalles = invoiceDetails();
  if (receiptDetails) payload.recepcion_detalles = receiptDetails();

  try {
   const result = await api(`${resource}/${editId ? editId + '/' : ''}`, payload);
   if (current === resource) {
    await load(resource);
    notice(resource === 'notas-credito'
     ? `Nota de crédito ${result.item?.numero_documento || ''} creada correctamente.`
     : 'Registro guardado.');
   }
  } catch (e) {
   notice(e.message, true);
  } finally {
   submitting = false;
   submit.disabled = false;
  }
 };

 if ($('editor').scrollIntoView) {
  $('editor').scrollIntoView({ behavior: 'smooth' });
 }
}