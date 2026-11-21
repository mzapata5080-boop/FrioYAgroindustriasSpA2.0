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

function formatSubtotal(quantity, price) {
 const q = scaledAmount(quantity), p = scaledAmount(price);
 if (q === null || p === null) return '—';
 const cents = (q * p + 50n) / 100n;
 return `$${(cents / 100n).toLocaleString('es-CL')},${(cents % 100n).toString().padStart(2, '0')} CLP`;
}

function attachReceiptDetails(form, context) {
 const articles = new Map((context.articles || []).map(a => [String(a.id), a.unidad_medida]));
 const units = { unidad: ['Unidades', 'unidad'], m: ['Metros', 'metro'], kg: ['Kilogramos', 'kilogramo'], l: ['Litros', 'litro'] };
 const article = form.elements.namedItem('articulo'), qty = form.elements.namedItem('cantidad'), price = form.elements.namedItem('precio');
 const box = node('div', undefined, 'mb-3');
 const unit = node('input'); unit.readOnly = true; unit.className = 'form-control'; unit.id = 'receipt-unit';
 const label = node('label', 'Unidad del artículo', 'form-label'); label.htmlFor = unit.id; box.append(label, unit);
 const total = node('p', 'Subtotal neto —', 'fw-semibold'); total.setAttribute('aria-live', 'polite');
 form.append(box, total);
 const priceLabel = form.querySelector('label[for="field-precio"]');

 function update() {
  const code = articles.get(article.value), info = units[code];
  unit.value = info ? info[0] : (code || 'Selecciona un artículo');
  if (priceLabel) priceLabel.textContent = info ? `Costo neto de compra por ${info[1]} (CLP)` : 'Costo unitario neto de compra (CLP)';
  qty.step = code === 'unidad' ? '1' : '0.01';
  qty.min = code === 'unidad' ? '1' : '0.01';
  total.textContent = `Subtotal neto ${formatSubtotal(qty.value, price.value)}`;
 }
 article.addEventListener('change', update); qty.addEventListener('input', update); price.addEventListener('input', update); update();
}

function attachInvoiceDetails(form, context, initialDetails, allowEmpty = false) {
 const articles = context.articles || [];
 const articleById = new Map(articles.map(article => [String(article.id), article]));
 const units = { unidad: 'Unidades', m: 'Metros', kg: 'Kilogramos', l: 'Litros' };
 const section = node('section', undefined, 'mb-3');
 const heading = node('h3', 'Artículos de la factura', 'h5');
 const rowsContainer = node('div');
 rowsContainer.id = 'invoice-details-list';
 const rows = [];
 const addButton = node('button', 'Agregar artículo', 'btn btn-outline-primary btn-sm mt-2');
 addButton.type = 'button';

 function addRow(detail = {}) {
  const index = rows.length + 1;
  const row = node('div', undefined, 'row g-2 align-items-end border rounded p-2 mb-2');
  const articleWrap = node('div', undefined, 'col-md-5');
  const articleLabel = node('label', 'Artículo', 'form-label');
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
  articleWrap.append(articleLabel, articleSelect);

  const quantityWrap = node('div', undefined, 'col-md-2');
  const quantityLabel = node('label', 'Cantidad', 'form-label');
  const quantity = node('input');
  quantity.type = 'number';
  quantity.className = 'form-control';
  quantity.min = '0.01';
  quantity.step = '0.01';
  quantity.required = true;
  quantity.value = detail.cantidad ?? '';
  quantityLabel.htmlFor = `invoice-detail-quantity-${index}`;
  quantity.id = quantityLabel.htmlFor;
  quantityWrap.append(quantityLabel, quantity);

  const priceWrap = node('div', undefined, 'col-md-3');
  const priceLabel = node('label', 'Precio unitario', 'form-label');
  const price = node('input');
  price.type = 'number';
  price.className = 'form-control';
  price.min = '0';
  price.step = '0.01';
  price.required = true;
  price.value = detail.precio_unitario ?? '';
  priceLabel.htmlFor = `invoice-detail-price-${index}`;
  price.id = priceLabel.htmlFor;
  priceWrap.append(priceLabel, price);

  const actionWrap = node('div', undefined, 'col-md-2');
  const removeButton = node('button', 'Quitar', 'btn btn-outline-danger w-100');
  removeButton.type = 'button';
  removeButton.onclick = () => { row.hidden = true; };
  actionWrap.append(removeButton);

  function updateQuantityStep() {
   const article = articleById.get(articleSelect.value);
   quantity.step = article && article.unidad_medida === 'unidad' ? '1' : '0.01';
   quantity.min = article && article.unidad_medida === 'unidad' ? '1' : '0.01';
   const unit = article ? (units[article.unidad_medida] || article.unidad_medida) : '';
   quantityLabel.textContent = unit ? `Cantidad (${unit})` : 'Cantidad';
  }
  articleSelect.addEventListener('change', updateQuantityStep);
  updateQuantityStep();

  row.append(articleWrap, quantityWrap, priceWrap, actionWrap);
  rowsContainer.append(row);
  rows.push({ row, articleSelect, quantity, price });
 }

 if (initialDetails && initialDetails.length) initialDetails.forEach(addRow);
 else if (!allowEmpty) addRow();
 addButton.onclick = () => addRow();
 section.append(heading, rowsContainer, addButton);
 form.append(section);

 return () => rows
  .filter(entry => !entry.row.hidden)
  .map(entry => ({
   articulo: entry.articleSelect.value,
   cantidad: entry.quantity.value,
   precio_unitario: entry.price.value
  }));
}

function attachOutputDetails(form, context) {
 const articles = new Map((context.articles || []).map(a => [String(a.id), a]));
 const units = { unidad: 'Unidades', m: 'Metros', kg: 'Kilogramos', l: 'Litros' };
 const article = form.elements.namedItem('articulo');
 const qty = form.elements.namedItem('cantidad');
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
  const stock = Number(item.stock_actual || 0);
  qty.step = code === 'unidad' ? '1' : '0.01';
  qty.min = code === 'unidad' ? '1' : '0.01';
  qty.max = String(stock);

  if (stock <= 0) {
   stockNotice.textContent = `Sin existencias en bodega (Stock: 0 ${unitLabel}).`;
   stockNotice.className = 'small fw-semibold mt-1 text-danger';
  } else {
   stockNotice.textContent = `Stock disponible en bodega: ${stock} ${unitLabel}`;
   stockNotice.className = 'small fw-semibold mt-1 text-success';
  }

  const entered = Number(qty.value || 0);
  if (entered > stock) {
   stockNotice.textContent = `La cantidad (${entered}) supera el stock disponible (${stock} ${unitLabel}).`;
   stockNotice.className = 'small fw-semibold mt-1 text-danger';
  }
 }
 article.addEventListener('change', update);
 qty.addEventListener('input', update);
 update();
}

function attachSolicitudDetails(form, context) {
 const articles = new Map((context.articles || []).map(a => [String(a.id), a]));
 const units = { unidad: 'Unidades', m: 'Metros', kg: 'Kilogramos', l: 'Litros' };
 const article = form.elements.namedItem('articulo');
 const qty = form.elements.namedItem('cantidad');
 if (!article || !qty) return;

 const box = node('div', undefined, 'mb-3');
 const unit = node('input'); unit.readOnly = true; unit.className = 'form-control'; unit.id = 'solicitud-unit';
 const label = node('label', 'Unidad de medida requerida', 'form-label'); label.htmlFor = unit.id;
 box.append(label, unit);

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
   return;
  }
  const code = item.unidad_medida;
  unit.value = units[code] || code;
  qty.step = code === 'unidad' ? '1' : '0.01';
  qty.min = code === 'unidad' ? '1' : '0.01';
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
  ingresos: 'Registrar ingreso',
  salidas: 'Registrar salida de bodega',
  solicitudes: 'Nueva solicitud de materiales'
 };
 $('editor-title').textContent = titles[resource] || (editId ? 'Editar registro' : 'Nuevo registro');

 const form = $('edit-form');
 form.replaceChildren();

 for (const field of fields) {
  const wrap = node('div', undefined, 'mb-3'), id = `field-${field.name}`;
  let input;

  if (field.type === 'select') {
   input = node('select');
   field.choices.forEach(([value, label]) => {
    const option = node('option', label);
    option.value = value;
    input.append(option);
   });
  } else if (field.type === 'textarea') {
   input = node('textarea');
  } else if (field.type === 'details') {
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
  } else {
   input.value = item[field.name] ?? (field.name === 'solicitud_id' ? requestId() : (field.initial ?? ''));
  }

  if (field.type === 'hidden') {
   wrap.hidden = true;
  } else {
   const label = node('label', field.label, 'form-label');
   label.htmlFor = id;
   wrap.append(label);
  }

  let hint;
  if (['ingresos', 'salidas', 'solicitudes'].includes(resource) && ['factura', 'articulo'].includes(field.name)) {
   hint = searchableSelect(input, field.label, wrap);
  }

  wrap.append(input);
  if (hint) wrap.append(hint);
  form.append(wrap);
 }

 const invoiceDetails = resource === 'facturas'
  ? attachInvoiceDetails(form, context, item.detalles, Boolean(editId && !item.detalles.length))
  : null;

 if (resource === 'ingresos') attachReceiptDetails(form, context);
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
   if (f.type === 'details') return;
   const input = form.elements.namedItem(f.name);
   payload[f.name] = f.type === 'checkbox' ? input.checked : input.value;
  });
  if (invoiceDetails) payload.detalles = invoiceDetails();

  try {
   await api(`${resource}/${editId ? editId + '/' : ''}`, payload);
   if (current === resource) {
    await load(resource);
    notice('Registro guardado.');
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
