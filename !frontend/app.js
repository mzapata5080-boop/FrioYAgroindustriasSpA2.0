'use strict';
const $ = id => document.getElementById(id);
let csrf = '', user = null, current = '', metadata = null, loadVersion = 0;
const names = {trabajadores:'Trabajadores',clientes:'Clientes',proveedores:'Proveedores',facturas:'Facturas de compra',articulos:'Inventario',categorias:'Categorías',ingresos:'Ingresos de bodega',salidas:'Salidas de bodega',kardex:'Kardex'};
function node(tag, text, cls) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; }
function notice(message, bad=false) { const n=node('div',message,`alert alert-${bad?'danger':'success'}`); $('notice').replaceChildren(n); }
async function api(path, payload) {
 const response=await fetch(`${window.API_BASE}/${path}`,{method:payload===undefined?'GET':'POST',credentials:'include',headers:payload===undefined?{}:{'Content-Type':'application/json','X-CSRFToken':csrf},body:payload===undefined?undefined:JSON.stringify(payload)});
 const body=await response.json().catch(()=>({error:`Respuesta inesperada (${response.status}). Comprueba el backend y la configuración CSRF.`}));
 if(!response.ok) { if(response.status===401){user=null;renderSession();} throw new Error(body.error || Object.entries(body.errors||{}).map(([k,v])=>`${k}: ${v.join(' ')}`).join('\n') || 'No se pudo completar la operación.'); }
 return body;
}
$('back').onclick=goHome;
$('home').onclick=event=>{event.preventDefault();if(user)goHome();};
const hiddenColumns=new Set(['password','solicitud_id','solicitud_salida']);
async function load(resource) {
 const version = ++loadVersion;
 const response = await api(`${resource}/`);
 if (version !== loadVersion) return false;
 current=resource; metadata=response; $('editor').hidden=true; $('new').hidden=true;
 $('dashboard').hidden=true; $('module-view').hidden=false;
 for(const button of $('modules').children){const active=button.dataset.resource===resource;button.classList.toggle('active',active);if(active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');}
 $('section-title').textContent=names[resource]; $('new').hidden=!metadata.can_write;
 const items=metadata.items; const table=node('table',undefined,'table table-hover align-middle text-start'); const head=node('thead');const tr=node('tr');
 const keys=items.length?Object.keys(items[0]).filter(k=>!hiddenColumns.has(k)):[];
 const labels={...Object.fromEntries((metadata.fields||[]).map(f=>[f.name,f.label])), responsable_id:'ID trabajador', responsable:'Trabajador', unidad_medida:'Unidad', articulo:'Artículo', fecha_registro:'Fecha y hora'};
 keys.forEach(k=>tr.append(node('th',labels[k]||k.replaceAll('_',' '))));
 if(metadata.can_write&&!['ingresos','salidas','kardex'].includes(resource))tr.append(node('th','Acciones'));
 head.append(tr);table.append(head);const tbody=node('tbody');
 items.forEach(item=>{const row=node('tr');keys.forEach(k=>row.append(node('td',typeof item[k]==='boolean'?(item[k]?'Sí':'No'):(k==='fecha_registro' ? new Date(item[k]).toLocaleString('es-CL') : (item[k]??'—')))));
 if(metadata.can_write&&!['ingresos','salidas','kardex'].includes(resource)){
 const actions=node('td'); const b=node('button','Editar','btn btn-sm btn-outline-primary');b.onclick=async()=>{try{const d=await api(`${resource}/${item.id}/`);showForm(d.fields,d.item);}catch(e){notice(e.message,true);}};actions.append(b);
 if(metadata.can_delete){const del=node('button','Eliminar','btn btn-sm btn-outline-danger ms-2');del.onclick=async()=>{if(!confirm('¿Eliminar este registro?'))return;try{await api(`${resource}/${item.id}/`,{_delete:true});await load(resource);notice('Registro eliminado.');}catch(e){notice(e.message,true);}};actions.append(del);}row.append(actions);}
 tbody.append(row);});table.append(tbody);$('records').replaceChildren(items.length?table:node('p','No hay registros.','text-muted'));
}
$('new').onclick=()=>showForm(metadata.fields);
$('login-form').onsubmit=async event=>{event.preventDefault();try{const d=await api('login/',{username:$('username').value,password:$('password').value});user=d.user;csrf=d.csrfToken;$('password').value='';$('notice').replaceChildren();renderSession();}catch(e){notice(e.message,true);}};
$('logout').onclick=async()=>{try{await api('logout/',{});const d=await api('session/');csrf=d.csrfToken;user=null;renderSession();}catch(e){notice(e.message,true);}};
(async()=>{try{const d=await api('session/');csrf=d.csrfToken;user=d.user;renderSession();}catch(e){notice(`No se pudo conectar: ${e.message}`,true);}})();
