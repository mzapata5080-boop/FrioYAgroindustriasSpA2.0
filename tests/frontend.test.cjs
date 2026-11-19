const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const {webcrypto} = require('node:crypto');

class Element {
 constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.value='';this.listeners={};this.attributes={};}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=[...nodes];}
 setAttribute(key,value){this.attributes[key]=value;}
 addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
 dispatchEvent(event){this[`on${event.type}`]?.(event);for(const fn of this.listeners[event.type]||[])fn(event);}
 scrollIntoView(){}
 get options(){return this.children;}
 find(predicate){for(const child of this.children){if(predicate(child))return child;const found=child.find(predicate);if(found)return found;}return null;}
 querySelector(selector){const match=selector.match(/^label\[for="(.+)"\]$/);return this.find(n=>n.tag==='label'&&n.htmlFor===match[1]);}
 get elements(){return {namedItem:name=>this.find(n=>n.name===name)};}
}
function context(){
 const nodes={editor:new Element('section'),'editor-title':new Element('h2'),'edit-form':new Element('form')};
 const ctx={window:{crypto:webcrypto},Event:class {constructor(type){this.type=type;}},current:'ingresos',
  metadata:{articles:[{id:1,unidad_medida:'kg'},{id:2,unidad_medida:'unidad'}]},
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
 assert.equal(ctx.formatSubtotal('20','2900'),'$58.000,00 CLP');
 assert.equal(ctx.formatSubtotal('1.50','1990'),'$2.985,00 CLP');
 assert.equal(ctx.formatSubtotal('0.01','0.50'),'$0,01 CLP');
 assert.equal(ctx.formatSubtotal('1.005','20'),'—');
 assert.equal(ctx.formatSubtotal('','20'),'—');
 assert.equal(ctx.formatSubtotal('1,50','1990'),'$2.985,00 CLP');
});
test('facturas y artículos se filtran por texto sin distinguir acentos',()=>{
 const {ctx,nodes}=context();ctx.showForm(fields);const form=nodes['edit-form'];
 const invoiceWrap=form.children.find(n=>n.find(x=>x.name==='factura'));
 const search=invoiceWrap.children.find(n=>n.type==='search');
 search.value='777';search.oninput();
 assert.equal(form.elements.namedItem('factura').options.length,2);
 assert.equal(form.elements.namedItem('factura').options[1].value,'7');
 search.value='perez';search.oninput();
 assert.equal(form.elements.namedItem('factura').options[1].value,'7');
 const articleWrap=form.children.find(n=>n.find(x=>x.name==='articulo'));
 const articleSearch=articleWrap.children.find(n=>n.type==='search');articleSearch.value='clavos';articleSearch.oninput();
 assert.equal(form.elements.namedItem('articulo').options[1].value,'1');
});
test('unidad, precio por kilogramo y subtotal se actualizan al seleccionar',()=>{
 const {ctx,nodes}=context();ctx.showForm(fields);const form=nodes['edit-form'];
 const article=form.elements.namedItem('articulo'), qty=form.elements.namedItem('cantidad'), price=form.elements.namedItem('precio');
 article.value='1';qty.value='1.50';price.value='1990';article.dispatchEvent(new ctx.Event('change'));
 assert.equal(form.find(n=>n.id==='receipt-unit').value,'Kilogramos');
 assert.equal(form.querySelector('label[for="field-precio"]').textContent,'Precio neto por kilogramo (CLP)');
 assert.ok(form.children.some(n=>n.textContent==='Subtotal neto $2.985,00 CLP'));
 article.value='2';article.dispatchEvent(new ctx.Event('change'));assert.equal(qty.step,'1');
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
