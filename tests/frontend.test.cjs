const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const {webcrypto} = require('node:crypto');

class Element {
 constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.value='';this.listeners={};this.attributes={};this.dataset={};}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=[...nodes];}
 setAttribute(key,value){this.attributes[key]=value;}
 addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
 dispatchEvent(event){this[`on${event.type}`]?.(event);for(const fn of this.listeners[event.type]||[])fn(event);}
 scrollIntoView(){}
 get options(){return this.children;}
 get selectedOptions(){return this.children.filter(option=>option.selected);}
 get text(){return (this.textContent + ' ' + this.children.map(c=>c.text).join(' ')).trim();}
 find(predicate){for(const child of this.children){if(predicate(child))return child;const found=child.find(predicate);if(found)return found;}return null;}
 querySelector(selector){const match=selector.match(/^label\[for="(.+)"\]$/);return this.find(n=>n.tag==='label'&&n.htmlFor===match[1]);}
 get elements(){return {namedItem:name=>this.find(n=>n.name===name)};}
}
function context(){
 const nodes={editor:new Element('section'),'editor-title':new Element('h2'),'edit-form':new Element('form')};
 const ctx={window:{crypto:webcrypto},Event:class {constructor(type){this.type=type;}},current:'ingresos',
  metadata:{
   invoiceDetails:[
    {id:101,factura_id:7,codigo_parte:'CL-01',articulo_nombre:'Clavos',unidad_medida:'kg',pendiente:'3.50'},
    {id:103,factura_id:7,codigo_parte:'TOR-01',articulo_nombre:'Tornillos',unidad_medida:'unidad',pendiente:'2'},
    {id:102,factura_id:8,codigo_parte:'TOR-01',articulo_nombre:'Tornillos',unidad_medida:'unidad',pendiente:'4'}
   ]
  },
  $:id=>nodes[id],node:(tag,text,cls)=>{const n=new Element(tag);if(text!==undefined)n.textContent=text;n.className=cls;return n;},
  notice:()=>{},api:async()=>({}),load:async()=>{}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../!frontend/forms.js'),'utf8'),ctx);
 return {ctx,nodes};
}
const fields=[
 {name:'solicitud_id',label:'Solicitud',type:'hidden',required:true},
 {name:'factura',label:'Factura',type:'select',required:true,choices:[['','Selecciona'],['7','777 — Proveedor Pérez'],['8','888 — Otro']]},
 {name:'articulo',label:'Artículo',type:'select',required:true,choices:[['','Selecciona'],['1','Clavos galvanizados'],['2','Tornillos']]},
 {name:'cantidad',label:'Cantidad',type:'number',required:true,step:'0.01',min:'0.01'},
 {name:'precio',label:'Precio',type:'number',required:true,step:'0.01',min:'0'},
];
test('subtotales exactos y redondeo equivalentes al backend',()=>{
 const {ctx}=context();
 assert.equal(ctx.formatSubtotal('20','2900'),'$58.000 CLP');
 assert.equal(ctx.formatSubtotal('1.50','1990'),'$2.985 CLP');
 assert.equal(ctx.formatSubtotal('0.01','0.50'),'$0,01 CLP');
 assert.equal(ctx.formatSubtotal('1.005','20'),'—');
 assert.equal(ctx.formatSubtotal('','20'),'—');
 assert.equal(ctx.formatSubtotal('1,50','1990'),'$2.985 CLP');
});
test('facturas filtran sus artículos pendientes',()=>{
 const {ctx,nodes}=context();ctx.showForm(fields);const form=nodes['edit-form'];
 const invoiceWrap=form.children.find(n=>n.find(x=>x.name==='factura'));
 const search=invoiceWrap.children.find(n=>n.type==='search');
 search.value='777';search.oninput();
 assert.equal(form.elements.namedItem('factura').options.length,2);
 assert.equal(form.elements.namedItem('factura').options[1].value,'7');
 const invoice=form.elements.namedItem('factura');
 invoice.value='7';invoice.dispatchEvent(new ctx.Event('change'));
 const line=form.find(n=>n.id==='receipt-detail-line-1');
 assert.equal(line.options.length,3);
 assert.equal(line.options[1].value,'101');
});
test('factura recibida muestra sus artículos en tabla solo lectura',()=>{
 const {ctx,nodes}=context();ctx.current='facturas';
 ctx.showForm([{name:'detalles',label:'Artículos de la factura',type:'details',required:true}],{
  id:9,detalles_bloqueados:true,
  detalles:[{articulo_nombre:'Válvula',cantidad:'2',precio_unitario:'1500.00'}]
 });
 const rows=nodes['edit-form'].find(n=>n.id==='invoice-details-list');
 const table=rows.find(n=>n.tag==='table');
 assert.ok(table);
 assert.deepEqual(table.find(n=>n.tag==='tr').children.map(cell=>cell.textContent),[
  'Artículo','Cantidad facturada','Precio unitario'
 ]);
 assert.deepEqual(table.find(n=>n.tag==='tbody').children[0].children.map(cell=>cell.textContent),[
  'Válvula','2','$1.500 CLP'
 ]);
 assert.equal(rows.find(n=>n.tag==='input'),null);
});
test('factura organiza los datos y calcula subtotales de artículos',()=>{
 const {ctx,nodes}=context();ctx.current='facturas';
 ctx.showForm([
  {name:'monto',label:'Monto total',type:'number',required:true,step:'1'},
  {name:'detalles',label:'Artículos de la factura',type:'details',required:true}
 ]);
 const form=nodes['edit-form'];
 assert.ok(form.find(n=>String(n.className || '').includes('invoice-fields-grid')));
 assert.ok(form.find(n=>String(n.className || '').includes('invoice-lines-table')));
 const quantity=form.find(n=>n.id==='invoice-detail-quantity-1');
 const price=form.find(n=>n.id==='invoice-detail-price-1');
 assert.equal(price.step,'0.01');
 quantity.value='2';quantity.dispatchEvent(new ctx.Event('input'));
 price.value='1000';price.dispatchEvent(new ctx.Event('input'));
 const summary=form.find(n=>String(n.className || '').includes('invoice-summary'));
 assert.equal(summary.children[0].children[1].textContent,'$2.000 CLP');
 const amount=form.elements.namedItem('monto');
 amount.value='1800';amount.dispatchEvent(new ctx.Event('input'));
 assert.equal(summary.children[1].children[1].textContent,'$1.800 CLP');
});
test('edición conserva los valores fraccionarios históricos sin permitir precios fraccionarios nuevos',()=>{
 const {ctx,nodes}=context();ctx.current='facturas';
 ctx.showForm([
  {name:'monto',label:'Monto total',type:'number',required:true,step:'1'},
  {name:'detalles',label:'Artículos de la factura',type:'details',required:true}
 ],{
  monto:'1000.50',
  detalles:[{id:12,articulo:1,cantidad:'1.25',precio_unitario:'100.50'}]
 });
 const form=nodes['edit-form'];
 assert.equal(form.elements.namedItem('monto').step,'0.01');
 assert.equal(form.find(n=>n.id==='invoice-detail-price-1').step,'0.01');
});
test('unidad, precio por kilogramo y subtotal se actualizan al seleccionar',()=>{
 const {ctx,nodes}=context();ctx.showForm(fields);const form=nodes['edit-form'];
 const invoice=form.elements.namedItem('factura');
 const line=form.find(n=>n.id==='receipt-detail-line-1');
 const qty=form.find(n=>n.id==='receipt-detail-quantity-1');
 invoice.value='7';invoice.dispatchEvent(new ctx.Event('change'));
 line.value='101';line.dispatchEvent(new ctx.Event('change'));
 assert.equal(qty.step,'0.01');
 assert.equal(qty.max,'3.50');
 invoice.value='8';invoice.dispatchEvent(new ctx.Event('change'));
 line.value='102';line.dispatchEvent(new ctx.Event('change'));
 assert.equal(qty.step,'1');
 assert.equal(qty.min,'1');
 assert.equal(qty.max,'4');
});
test('una recepción envía varias líneas de la factura seleccionada',async()=>{
 const {ctx,nodes}=context();const payloads=[];
 ctx.api=async(path,payload)=>{payloads.push(payload);return {};};
 ctx.showForm(fields);const form=nodes['edit-form'];
 const invoice=form.elements.namedItem('factura');
 invoice.value='7';invoice.dispatchEvent(new ctx.Event('change'));
 const first=form.find(n=>n.id==='receipt-detail-line-1');
 first.value='101';first.dispatchEvent(new ctx.Event('change'));
 form.find(n=>n.id==='receipt-detail-quantity-1').value='1.50';
 form.find(n=>n.textContent==='Agregar otro artículo').onclick();
 const second=form.find(n=>n.id==='receipt-detail-line-2');
 second.value='103';second.dispatchEvent(new ctx.Event('change'));
 form.find(n=>n.id==='receipt-detail-quantity-2').value='1';
 await form.onsubmit({preventDefault(){}});
 assert.deepEqual(JSON.parse(JSON.stringify(payloads[0].recepcion_detalles)),[
  {detalle_factura:'101',cantidad:'1.50'},
  {detalle_factura:'103',cantidad:'1'}
 ]);
});
test('reintentar después de un error conserva el UUID de la solicitud',async()=>{
 const {ctx,nodes}=context();const payloads=[];
 ctx.api=async(path,payload)=>{payloads.push(payload);if(payloads.length===1)throw new Error('Sin conexión');return {};};
 ctx.showForm(fields);const form=nodes['edit-form'];
 await form.onsubmit({preventDefault(){}});await form.onsubmit({preventDefault(){}});
 assert.equal(payloads.length,2);assert.equal(payloads[0].solicitud_id,payloads[1].solicitud_id);
 assert.match(payloads[0].solicitud_id,/^[a-f0-9-]{36}$/);
});
test('dos envíos mientras espera una respuesta producen una sola petición',async()=>{
 const {ctx,nodes}=context();let release,calls=0;
 ctx.api=()=>{calls++;return new Promise(resolve=>{release=resolve;});};
 ctx.showForm(fields);const form=nodes['edit-form'];
 const first=form.onsubmit({preventDefault(){}});await form.onsubmit({preventDefault(){}});
 assert.equal(calls,1);release({});await first;
});

function outputContext() {
  const nodes = { editor: new Element('section'), 'editor-title': new Element('h2'), 'edit-form': new Element('form') };
  const ctx = {
    window: { crypto: webcrypto },
    Event: class { constructor(type) { this.type = type; } },
    current: 'salidas',
    metadata: {
      articles: [
        { id: 1, codigo_parte: 'CL-01', descripcion: 'Clavos', unidad_medida: 'kg', stock_actual: '15.50' },
        { id: 2, codigo_parte: 'VAL-01', descripcion: 'Válvula', unidad_medida: 'unidad', stock_actual: '4' }
      ],
      works: [{ id: 5, cliente_id: 7, codigo_ot: 'OT-2026-05' }],
      materialRequests: [{ id: 11, obra_id: 5, articulo_id: 2, cantidad_pendiente: '3' }]
    },
    $: id => nodes[id],
    node: (tag, text, cls) => { const n = new Element(tag); if (text !== undefined) n.textContent = text; n.className = cls; return n; },
    notice: () => {},
    api: async () => ({}),
    load: async () => {}
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../!frontend/forms.js'), 'utf8'), ctx);
  return { ctx, nodes };
}

test('en salidas la unidad y el stock disponible se toman desde el artículo', () => {
  const { ctx, nodes } = outputContext();
  const salidaFields = [
    { name: 'solicitud_id', label: 'Solicitud', type: 'hidden', required: true },
    { name: 'articulo', label: 'Artículo', type: 'select', required: true, choices: [['', 'Selecciona'], ['1', 'Clavos'], ['2', 'Válvula']] },
    { name: 'cantidad', label: 'Cantidad', type: 'number', required: true, step: '0.01', min: '0.01' },
    { name: 'numero_ot', label: 'Orden de trabajo / obra', type: 'text', required: true }
  ];
  ctx.showForm(salidaFields);
  const form = nodes['edit-form'];
  const article = form.elements.namedItem('articulo');
  const qty = form.elements.namedItem('cantidad');

  article.value = '1';
  article.dispatchEvent(new ctx.Event('change'));
  assert.equal(form.find(n => n.id === 'output-unit').value, 'Kilogramos');
  assert.equal(qty.step, '0.01');
  assert.equal(qty.max, '15.5');

  article.value = '2';
  article.dispatchEvent(new ctx.Event('change'));
  assert.equal(form.find(n => n.id === 'output-unit').value, 'Unidades');
  assert.equal(qty.step, '1');
  assert.equal(qty.max, '4');
});

test('al elegir una obra en una salida se completan cliente y número OT', () => {
  const { ctx, nodes } = outputContext();
  ctx.showForm([
    { name: 'articulo', label: 'Artículo', type: 'select', required: true, choices: [['', 'Selecciona'], ['1', 'Clavos']] },
    { name: 'cantidad', label: 'Cantidad', type: 'number', required: true, step: '0.01', min: '0.01' },
    { name: 'obra', label: 'Obra', type: 'select', required: false, choices: [['', 'Selecciona'], ['5', 'OT-2026-05']] },
    { name: 'cliente', label: 'Cliente', type: 'select', required: false, choices: [['', 'Selecciona'], ['7', 'Cliente 7']] },
    { name: 'numero_ot', label: 'Número OT', type: 'text', required: false }
  ]);
  const form = nodes['edit-form'];
  const work = form.elements.namedItem('obra');
  const client = form.elements.namedItem('cliente');
  const workOrder = form.elements.namedItem('numero_ot');

  work.value = '5';
  work.dispatchEvent(new ctx.Event('change'));

  assert.equal(client.value, '7');
  assert.equal(workOrder.value, 'OT-2026-05');
});

test('al elegir una solicitud aprobada se completan obra, cliente, artículo y cantidad pendiente', () => {
  const { ctx, nodes } = outputContext();
  ctx.showForm([
    { name: 'solicitud_material', label: 'Solicitud aprobada', type: 'select', required: false, choices: [['', 'Selecciona'], ['11', 'Solicitud 11']] },
    { name: 'obra', label: 'Obra', type: 'select', required: false, choices: [['', 'Selecciona'], ['5', 'OT-2026-05']] },
    { name: 'cliente', label: 'Cliente', type: 'select', required: false, choices: [['', 'Selecciona'], ['7', 'Cliente 7']] },
    { name: 'articulo', label: 'Artículo', type: 'select', required: true, choices: [['', 'Selecciona'], ['1', 'Clavos'], ['2', 'Válvula']] },
    { name: 'cantidad', label: 'Cantidad', type: 'number', required: true, step: '0.01', min: '0.01' },
    { name: 'numero_ot', label: 'Número OT', type: 'text', required: false }
  ]);
  const form = nodes['edit-form'];
  const materialRequest = form.elements.namedItem('solicitud_material');
  materialRequest.value = '11';
  materialRequest.dispatchEvent(new ctx.Event('change'));

  assert.equal(form.elements.namedItem('obra').value, '5');
  assert.equal(form.elements.namedItem('cliente').value, '7');
  assert.equal(form.elements.namedItem('articulo').value, '2');
  assert.equal(form.elements.namedItem('cantidad').value, '3');
  assert.equal(form.elements.namedItem('numero_ot').value, 'OT-2026-05');
});

test('en obras se eligen varios técnicos desde el desplegable y aparecen enumerados', async () => {
  const { ctx, nodes } = context();
  const payloads = [];
  ctx.current = 'obras';
  ctx.api = async (path, payload) => { payloads.push(payload); return {}; };
  ctx.showForm([{
    name: 'tecnicos', label: 'Técnicos asignados', type: 'select', multiple: true,
    required: false, choices: [['1', 'Ana Pérez'], ['2', 'Luis Soto']]
  }]);

  const form = nodes['edit-form'];
  const select = form.elements.namedItem('tecnicos');
  const menu = form.find(n => n.id === 'field-tecnicos-choices');
  const toggle = form.find(n => n.tag === 'button' && n.textContent === 'Seleccionar técnicos');
  assert.equal(select.hidden, true);
  toggle.onclick();
  assert.equal(menu.hidden, false);

  const checkboxes = menu.children.map(label => label.children[0]);
  checkboxes[0].checked = true;
  checkboxes[0].onchange();
  checkboxes[1].checked = true;
  checkboxes[1].onchange();
  const selected = form.find(n => n.tag === 'ol');
  assert.deepEqual(selected.children.map(item => item.textContent), ['Ana Pérez', 'Luis Soto']);

  await form.onsubmit({ preventDefault() {} });
  assert.deepEqual(JSON.parse(JSON.stringify(payloads[0].tecnicos)), ['1', '2']);
});

function dashboardContext(user) {
  const nodes = {
    'login-panel': new Element('section'),
    'workspace': new Element('section'),
    'logout': new Element('button'),
    'identity': new Element('span'),
    'welcome': new Element('h1'),
    'dashboard': new Element('section'),
    'module-view': new Element('section'),
    'editor': new Element('section'),
    'records': new Element('div'),
    'new': new Element('button'),
    'modules': new Element('nav'),
    'role-cards': new Element('div'),
    'warehouse-actions': new Element('div'),
    'additional-actions': new Element('div'),
    'additional-modules': new Element('details'),
    'notice': new Element('div')
  };
  const ctx = {
    user,
    names: {
      trabajadores: 'Trabajadores', clientes: 'Clientes', proveedores: 'Proveedores',
      facturas: 'Facturas de compra', articulos: 'Inventario', categorias: 'Categorías',
      ingresos: 'Ingresos de bodega', salidas: 'Salidas de bodega', kardex: 'Kardex',
      obras: 'Obras', presupuestos: 'Presupuestos',
      solicitudes: 'Solicitudes de materiales'
    },
    $: id => nodes[id],
    node: (tag, text, cls) => { const n = new Element(tag); if (text !== undefined) n.textContent = text; n.className = cls; return n; },
    notice: () => {},
    api: async () => ({}),
    load: async () => {},
    showForm: () => {},
    abrirOperaciones: () => {},
    current: '',
    metadata: null,
    loadVersion: 0
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../!frontend/dashboard.js'), 'utf8'), ctx);
  return { ctx, nodes };
}

test('bodega ve botones de inventario, ingresos, salidas y categorías pero no finanzas ni personal', () => {
  const { ctx, nodes } = dashboardContext({ username: 'bodeguero', rol: 'bodega', name: 'Pedro Bodega', is_superuser: false });
  ctx.renderSession();
  const whButtons = nodes['warehouse-actions'].children.map(b => b.textContent);
  assert.ok(whButtons.includes('Crear artículo'));
  assert.ok(whButtons.includes('Registrar ingreso'));
  assert.ok(whButtons.includes('Registrar salida'));
  assert.ok(whButtons.includes('Categorías'));
  assert.ok(whButtons.includes('Solicitudes de obra'));

  const navTabs = nodes['modules'].children.map(b => b.textContent);
  assert.ok(navTabs.includes('Inventario'));
  assert.ok(navTabs.includes('Categorías'));
  assert.ok(navTabs.includes('Ingresos de bodega'));
  assert.ok(navTabs.includes('Salidas de bodega'));
  assert.ok(navTabs.includes('Solicitudes de materiales'));
  assert.ok(!navTabs.includes('Trabajadores'));
  assert.ok(!navTabs.includes('Facturas de compra'));
});

test('supervisor de obra ve tarjeta de supervisión y solicitudes sin permisos de bodega ni finanzas', () => {
  const { ctx, nodes } = dashboardContext({ username: 'sup1', rol: 'Supervisor de Obra', name: 'Carlos Ruiz', is_superuser: false });
  ctx.renderSession();
  const roleCards = nodes['role-cards'].children.map(c => c.text).join(' ');
  assert.ok(roleCards.includes('Supervisión de Obras y Terreno'));
  assert.ok(roleCards.includes('Mis Obras'));
  assert.ok(roleCards.includes('Mis solicitudes'));

  const navTabs = nodes['modules'].children.map(b => b.dataset.resource);
  assert.ok(navTabs.includes('obras'));
  assert.ok(navTabs.includes('presupuestos'));
  assert.ok(navTabs.includes('solicitudes'));
  assert.ok(!navTabs.includes('salidas'));
  assert.ok(!navTabs.includes('facturas'));
});

test('facturas permiten agregar y enviar varios artículos en una sola operación', async () => {
  const nodes = {
    editor: new Element('section'),
    'editor-title': new Element('h2'),
    'edit-form': new Element('form')
  };
  const payloads = [];
  const ctx = {
    window: { crypto: webcrypto },
    Event: class { constructor(type) { this.type = type; } },
    current: 'facturas',
    metadata: {
      articles: [
        { id: 1, codigo_parte: 'CL-01', descripcion: 'Clavos', unidad_medida: 'kg' },
        { id: 2, codigo_parte: 'TOR-01', descripcion: 'Tornillos', unidad_medida: 'unidad' }
      ]
    },
    $: id => nodes[id],
    node: (tag, text, cls) => {
      const n = new Element(tag);
      if (text !== undefined) n.textContent = text;
      n.className = cls;
      return n;
    },
    notice: () => {},
    api: async (path, payload) => { payloads.push(payload); return {}; },
    load: async () => {}
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../!frontend/forms.js'), 'utf8'), ctx);

  ctx.showForm([
    { name: 'numero_documento', label: 'Documento', type: 'text', required: true },
    { name: 'monto', label: 'Monto', type: 'number', required: true, step: '0.01' },
    { name: 'observaciones', label: 'Observaciones', type: 'textarea', required: false },
    { name: 'detalles', label: 'Artículos', type: 'details', required: true }
  ]);
  const form = nodes['edit-form'];
  const rows = form.find(n => n.id === 'invoice-details-list').find(n => n.tag === 'tbody');
  const addButton = form.find(n => n.textContent === 'Agregar artículo');
  addButton.onclick();
  assert.equal(rows.children.length, 2);

  const first = rows.children[0];
  first.children[0].children[1].value = '1';
  first.children[1].children[1].value = '1.50';
  first.children[2].children[1].value = '100';
  const second = rows.children[1];
  second.children[0].children[1].value = '2';
  second.children[1].children[1].value = '2';
  second.children[2].children[1].value = '50';

  await form.onsubmit({ preventDefault() {} });
  assert.deepEqual(JSON.parse(JSON.stringify(payloads[0].detalles)), [
    { articulo: '1', cantidad: '1.50', precio_unitario: '100', descuento_1: '0', descuento_2: '0', descuento_3: '0', precio_lista: '' },
    { articulo: '2', cantidad: '2', precio_unitario: '50', descuento_1: '0', descuento_2: '0', descuento_3: '0', precio_lista: '' }
  ]);

  ctx.showForm([
    { name: 'numero_documento', label: 'Documento', type: 'text', required: true },
    { name: 'monto', label: 'Monto', type: 'number', required: true, step: '0.01' },
    { name: 'observaciones', label: 'Observaciones', type: 'textarea', required: false },
    { name: 'detalles', label: 'Artículos', type: 'details', required: true }
  ], { id: 20, numero_documento: 'F-020', monto: '50', detalles: [] });
  assert.equal(
    nodes['edit-form'].find(n => n.id === 'invoice-details-list').find(n => n.tag === 'tbody').children.length,
    0
  );
  await nodes['edit-form'].onsubmit({ preventDefault() {} });
  assert.deepEqual(JSON.parse(JSON.stringify(payloads[1].detalles)), []);
});
